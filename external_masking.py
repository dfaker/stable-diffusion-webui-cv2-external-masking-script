import math
import os
import sys
import traceback


import cv2
from PIL import Image
import numpy as np

lastx,lasty=None,None

def display_mask_ui(image,mask,max_size,initPolys):

  polys = initPolys

  def on_mouse(event, x, y, buttons, param):
    global lastx,lasty

    lastx,lasty = x,y

    if event == cv2.EVENT_LBUTTONDOWN:
      polys[-1].append((x,y))
    elif event == cv2.EVENT_RBUTTONDOWN:
      polys.append([])

  opencvImage = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

  if mask is None:
    opencvMask  = cv2.cvtColor( np.array(opencvImage) , cv2.COLOR_BGR2GRAY)
  else:
    opencvMask  = np.array(mask)


  maxdim = max(opencvImage.shape[1],opencvImage.shape[0])

  factor = max_size/maxdim

  opencvImage = cv2.resize(opencvImage, (int(opencvImage.shape[1]*factor),int(opencvImage.shape[0]*factor)))

  cv2.namedWindow('MaskingWindow', cv2.WINDOW_AUTOSIZE)
  cv2.setWindowProperty('MaskingWindow', cv2.WND_PROP_TOPMOST, 1)
  cv2.setMouseCallback('MaskingWindow', on_mouse)

  font = cv2.FONT_HERSHEY_SIMPLEX

  srcImage = opencvImage.copy()
  combinedImage = opencvImage.copy()

  while 1:

    foreground    = np.zeros_like(srcImage)

    for i,polyline in enumerate(polys):
      if len(polyline)>0:

        segs = polyline[::]

        print(i,len(polys),lastx,lasty)
        active=False
        if len(polys[-1])>0 and i==len(polys)-1 and lastx is not None:
          segs = polyline+[(lastx,lasty)]
          active=True

        if active:
          cv2.fillPoly(foreground, np.array([segs]), ( 190, 107,  253), 0)
        else:
          cv2.fillPoly(foreground, np.array([segs]), (255, 255, 255), 0)


    foreground[foreground<1] = srcImage[foreground<1]
    combinedImage = cv2.addWeighted(srcImage, 0.5, foreground, 0.5, 0)

    helpText='Q=Save, C=Reset, LeftClick=Add new point to polygon, Rightclick=Close polygon'
    combinedImage = cv2.putText(combinedImage, helpText, (0,11), font, 0.4, (0,0,0), 2, cv2.LINE_AA)
    combinedImage = cv2.putText(combinedImage, helpText, (0,11), font, 0.4, (255,255,255), 1, cv2.LINE_AA)

    cv2.imshow('MaskingWindow',combinedImage)

    try:
      key = cv2.waitKey(1)
      if key == ord('q'):
        if len(polys[0])>0:
          newmask = np.zeros_like(cv2.cvtColor( opencvMask.astype('uint8') ,cv2.COLOR_GRAY2BGR) )
          for i,polyline in enumerate(polys):
            if len(polyline)>0:
              segs = [(int(a/factor),int(b/factor)) for a,b in polyline]
              cv2.fillPoly(newmask, np.array([segs]), (255,255,255), 0)
          cv2.destroyWindow('MaskingWindow')
          return Image.fromarray( cv2.cvtColor( newmask, cv2.COLOR_BGR2GRAY) ),polys
        break
      if key == ord('c'):
        polys = [[]]

    except Exception as e:
      print(e)
      break

  cv2.destroyWindow('MaskingWindow')
  return mask,polys

import modules.scripts as scripts
import gradio as gr

from modules.processing import Processed, process_images
from modules.shared import opts, cmd_opts, state

class Script(scripts.Script):

    def title(self):
        return "External Image Masking"

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        if not is_img2img:
            return None

        initialSize = 1024

        try:
          import tkinter as tk
          root = tk.Tk()
          screen_width  = int(root.winfo_screenwidth())
          screen_height = int(root.winfo_screenheight())
          print(screen_width,screen_height)
          initialSize = min(screen_width,screen_height)-50
          print(initialSize)
        except Exception as e:
          print(e)

        max_size = gr.Slider(label="Masking preview size", minimum=512, maximum=initialSize*2, step=8, value=initialSize)
        with gr.Row():
          ask_on_each_run      = gr.Checkbox(label='Draw new mask on every run', value=False)
          non_contigious_split = gr.Checkbox(label='Process non-contigious masks separately', value=False)

        return [max_size,ask_on_each_run,non_contigious_split]

    def run(self, p, max_size, ask_on_each_run, non_contigious_split):

        if not hasattr(self,'lastImg'):
          self.lastImg = None

        if not hasattr(self,'lastMask'):
          self.lastMask = None

        if not hasattr(self,'lastPolys'):
          self.lastPolys = [[]]

        if ask_on_each_run or self.lastImg is None or self.lastImg != p.init_images[0]:

          if self.lastImg is None or self.lastImg != p.init_images[0]:
            self.lastPolys = [[]]

          p.image_mask,self.lastPolys  = display_mask_ui(p.init_images[0],p.image_mask,max_size,self.lastPolys)
          self.lastImg  = p.init_images[0]
          if p.image_mask is not None:
            self.lastMask = p.image_mask.copy()
        elif hasattr(self,'lastMask') and self.lastMask is not None:
          p.image_mask = self.lastMask.copy()

        if non_contigious_split:
          maskImgArr = np.array(p.image_mask)
          ret, markers = cv2.connectedComponents(maskImgArr)
          markerCount = markers.max()

          if markerCount > 1:
            tempimages = []
            tempMasks  = []
            for maski in range(1,markerCount+1):
              print('maski',maski)
              maskSection = np.zeros_like(maskImgArr)
              maskSection[markers==maski] = 255
              p.image_mask = Image.fromarray( maskSection.copy() )
              proc = process_images(p)
              images = proc.images
              tempimages.append(np.array(images[0]))
              tempMasks.append(np.array(maskSection.copy()))

            finalImage = tempimages[0].copy()

            for outimg,outmask in zip(tempimages,tempMasks):
              finalImage[outmask==255] = outimg[outmask==255]
            images = [finalImage]


          else:
            proc = process_images(p)
            images = proc.images
        else:
          proc = process_images(p)
          images = proc.images

        return Processed(p, images, p.seed, "")
