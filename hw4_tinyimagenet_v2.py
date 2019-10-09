# -*- coding: utf-8 -*-
"""hw4_TinyImageNet.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1j3d3Wu1wMLYvcjKtm2utiPCn6cU0DwWl
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
import torchvision
from torchvision import datasets, transforms
from PIL import Image
import torch.distributed as dist

import os
import subprocess
#from mpi4py import MPI
import h5py
import time

batch_size=128
LR=0.001
Num_Epochs=500
num_output=200
scheduler_step_size=50
scheduler_gamma=0.5

# device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')

transform_train=transforms.Compose([transforms.RandomCrop(64, padding=4),
                  transforms.RandomHorizontalFlip(),
                  #transforms.RandomVerticalFlip(),
                  transforms.ToTensor(),
                  transforms.Normalize(mean=[0.507, 0.487, 0.441], std=[0.267, 0.256, 0.276])])
transform_val=transforms.Compose([transforms.ToTensor(),transforms.Normalize(mean=[0.507, 0.487, 0.441], std=[0.267, 0.256, 0.276])])

def create_val_folder(val_dir):
  path=os.path.join(val_dir,'images')
  filename=os.path.join(val_dir,'val_annotations.txt')
  fp=open(filename,"r")
  data=fp.readlines()

  val_img_dict={}
  for line in data:
    words=line.split("\t")
    val_img_dict[words[0]]=words[1]
  fp.close()
  for img, folder in val_img_dict.items():
    newpath=(os.path.join(path,folder))
    if not os.path.exists(newpath):
      os.makedirs(newpath)
    if os.path.exists(os.path.join(path,img)):
      os.rename(os.path.join(path,img),os.path.join(newpath,img))
  return

train_dir='/u/training/tra323/tiny-imagenet-200/train'
train_dataset=datasets.ImageFolder(train_dir,transform=transform_train)
#print(train_dataset.class_to_idx)
train_loader=torch.utils.data.DataLoader(train_dataset,batch_size=batch_size,shuffle=True, num_workers=8)

val_dir='/u/training/tra323/tiny-imagenet-200/val/'
if 'val_' in os.listdir(val_dir+'images/')[0]:
  create_val_folder(val_dir)
  val_dir=val_dir+'images/'
else:
  val_dir=val_dir+'images/'

val_dataset=datasets.ImageFolder(val_dir,transform=transform_val)
#print(val_dataset,class_to_idx)
val_loader=torch.utils.data.DataLoader(val_dataset,batch_size=batch_size,shuffle=False,num_workers=8)

# batch_size=128
# LR=0.001
# Num_Epochs=500
# num_output=100
# scheduler_step_size=50
# scheduler_gamma=0.5

class BasicBlock(nn.Module):
  def __init__(self,inplanes,planes,stride,padding,downsample=None):
    super(BasicBlock,self).__init__()
    self.conv1=nn.Conv2d(inplanes,planes,kernel_size=3,stride=stride,padding=padding)
    #self.conv1=conv3x3(inplanes,planes,stride)
    self.bn1=nn.BatchNorm2d(planes)
    self.relu=nn.ReLU(inplace=True)
    self.conv2=nn.Conv2d(planes,planes,kernel_size=3,stride=1,padding=padding) #stride should be 1 for the second conv
    #self.conv2=conv3x3(planes,planes)
    self.bn2=nn.BatchNorm2d(planes)
    self.downsample=downsample
    self.stride=stride
  def forward(self,x):
    residual=x
    out=self.conv1(x)
    out=self.bn1(out)
    out=self.relu(out)
    out=self.conv2(out)
    out=self.bn2(out)
    if self.downsample is not None:
      residual = self.downsample(x)
    #print(residual.shape)
    #print(out.shape)
    out+=residual
    out=self.relu(out)
    return out

class ResNet(nn.Module):
  def __init__(self):
    super(ResNet,self).__init__()
    self.conv3=nn.Conv2d(3,32,3,stride=1,padding=1)#32, kernel_size=3, stride=1, padding=1 [32,64,64]
    self.bn3=nn.BatchNorm2d(32)
    self.relu1=nn.ReLU(inplace=True)
    self.dropout=nn.Dropout(p=0.5)

    #self.downsample1=nn.Conv2d(3,32,kernel_size=1,stride=1)
    self.bb1=BasicBlock(32,32,1,1,downsample=None) #[32,64,64]
    self.bb2=BasicBlock(32,32,1,1,downsample=None)
    #self.dropout1=nn.Dropout(p=0.5)
    
    self.downsample1=nn.Sequential(nn.Conv2d(32,64,kernel_size=3,stride=2,padding=1),nn.BatchNorm2d(64))
    #self.downsample1=nn.Conv2d(32,64,kernel_size=3,stride=2,padding=1)
    self.bb3=BasicBlock(32,64,2,1,downsample=self.downsample1) #[64,32,32]
    self.bb4=BasicBlock(64,64,1,1,downsample=None)
    self.bb5=BasicBlock(64,64,1,1,downsample=None)
    self.bb6=BasicBlock(64,64,1,1,downsample=None)
    #self.dropout2=nn.Dropout(p=0.5)

    self.downsample2=nn.Sequential(nn.Conv2d(64,128,kernel_size=3,stride=2,padding=1),nn.BatchNorm2d(128)) 
    #self.downsample2=nn.Conv2d(64,128,kernel_size=1,stride=2)
    self.bb7=BasicBlock(64,128,2,1,downsample=self.downsample2) #[128,16,16]
    self.bb8=BasicBlock(128,128,1,1,downsample=None)
    self.bb9=BasicBlock(128,128,1,1,downsample=None)
    self.bb10=BasicBlock(128,128,1,1,downsample=None)
    #self.dropout3=nn.Dropout(p=0.5)
    
    self.downsample3=nn.Sequential(nn.Conv2d(128,256,kernel_size=3,stride=2,padding=1),nn.BatchNorm2d(256))
    #self.downsample3=nn.Conv2d(128,256,kernel_size=1,stride=2)
    self.bb11=BasicBlock(128,256,2,1,downsample=self.downsample3) #[256,8,8]
    self.bb12=BasicBlock(256,256,1,1,downsample=None)
    #self.dropout4=nn.Dropout(p=0.7)

    self.maxpool=nn.MaxPool2d(kernel_size=4,stride=2)#[256,2,2]
    self.fc1=nn.Linear(3*3*256,num_output)
    # self.bn4=nn.BatchNorm1d(512)
    # self.fc2=nn.Linear(512,num_output)


  def forward(self,x):
    out=self.conv3(x) #output size=32,32,32
    out=self.bn3(out)
    out=self.relu1(out)
    out=self.dropout(out)
    #print(out.size)

    #stack1
    out=self.bb1(out)#(in_channels,out_channels,stride)#[32,32,1]
    out=self.bb2(out)
    #out=self.dropout1(out)

    #stack2
    out=self.bb3(out)
    out=self.bb4(out)
    out=self.bb5(out)
    out=self.bb6(out)
    #out=self.dropout2(out)

    #stack3
    out=self.bb7(out)
    out=self.bb8(out)
    out=self.bb9(out)
    out=self.bb10(out)
    #out=self.dropout3(out)

    #stack4
    out=self.bb11(out)
    out=self.bb12(out)
    #out=self.dropout4(out)

    #max pool
    out=self.maxpool(out)
    #print(out.shape)

    #fully connected
    out=out.view(-1,2*2*256) #flatten
    out=self.fc1(out)
    # out=self.bn4(out)
    # out=self.fc2(out)
    #print(out.shape)
    return out

# device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
#basic_block=BasicBlock().to(device)
resnet=ResNet().cuda()

criterion=nn.CrossEntropyLoss()
#optimizer=torch.optim.RMSprop(resnet.parameters(),lr=LR,weight_decay=0.0005)
#scheduler=torch.optim.lr_scheduler.StepLR(optimizer,step_size=scheduler_step_size,gamma=scheduler_gamma)
optimizer=torch.optim.Adam(resnet.parameters(),lr=LR)

start_time=time.time()

for epoch in range(Num_Epochs):
  #scheduler.step()
  resnet.train()
  total = 0
  correct = 0
  start_time = time.time()
  for images,labels in train_loader:
    images=Variable(images.cuda())
    labels=Variable(labels.cuda())
    outputs=resnet(images)
    #print(outputs.shape)
    
    optimizer.zero_grad()
    loss = criterion(outputs, labels)
    _,predicted = torch.max(outputs,1)
    total += labels.size(0)
    
    correct += (predicted == labels).sum().item()
  
    loss.backward()

    if(epoch>6):
      for group in optimizer.param_groups:
        for p in group['params']:
          state = optimizer.state[p]
          if 'step' in state.keys():
            if(state['step']>=1024):
              state['step'] = 1000

    optimizer.step()
  
  train_accuracy = correct/total
  
  with torch.no_grad():
    resnet.eval()
    correct=0
    total=0
    for images,labels in val_loader:
      #images,labels = data
      images = Variable(images.cuda())
      labels = Variable(labels.cuda())
      outputs = resnet(images)
        

      total += labels.size(0)
      _,predicted = torch.max(outputs,1)
      correct += (predicted == labels).sum().item()
    test_accuracy = correct/total
  
  print("Epoch {0} Time {1:.4f} Train Acc {2:.4f} Test Acc {3:.4f}".format(epoch, round(time.time()-start_time,4), round(train_accuracy,4), round(test_accuracy,4)))
  torch.save(resnet.state_dict(),'epoch-{}.ckpt'.format(epoch))
