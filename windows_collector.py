from configparser import ConfigParser
from PIL import Image
from PIL import ImageFilter
import win32process
import numpy as np
import math
from ctypes import windll
import time
import ctypes
from ctypes import *
from ctypes.wintypes import *
from functools import partial
import time
import random
import win32gui
import win32ui
import win32con
import ctypes
import sys

config = ConfigParser()
config.read('win_capture_config.ini')
if config['DEFAULT']['Configed'] == 'False':
    raise Exception('Please confirm the settings in config and then set Configed to True')
    
gdi_path = config['DEFAULT']['WinGDIPath']
gdi = ctypes.WinDLL(gdi_path)

class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ('biSize', DWORD),
        ('biWidth', LONG),
        ('biHeight', LONG),
        ('biPlanes', WORD),
        ('biBitCount', WORD),
        ('biCompression', DWORD),
        ('biSizeImage', DWORD),
        ('biXPelsPerMeter', LONG),
        ('biYPelsPerMeter', LONG),
        ('biClrUsed', DWORD),
        ('biClrImportant', DWORD),
        ]

    def __init__(self, w, h):
        self.biSize = sizeof(self)
        self.biWidth = w
        self.biHeight = h
        self.biPlanes = 1
        self.biBitCount = 24
        self.biSizeImage = w * h * 3


class WindowsScreenFetcher:
    def __init__(self):
        self.parse_config()
        self.goi_hwnd = self.get_game_window_handle()
        self.get_device_contexts()
        self.pid = self.get_pid(self.goi_hwnd)
       
    def get_pid(self, hwnd):
        thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid
        
    def get_game_window_handle(self):
        goi_hwnd = win32gui.FindWindow(None, "Getting Over It")
        if goi_hwnd == 0:
            raise Exception('Unable to find the game window')
        return goi_hwnd

    def parse_config(self):
        #luckily the width divides 4, so we dont have to allocate additional space to account for stride
        config = ConfigParser()
        config.read('win_capture_config.ini')
        self.game_height = int(config['DEFAULT']['GameHeight'])
        self.game_width = int(config['DEFAULT']['GameWidth'])
        self.screenshot_dir = config['DEFAULT']['ScreenshotDirPath']
        
        #might not need this
        self.game_width_offset = int(config['DEFAULT']['GameWidthOffset'])
        self.game_height_offset = int(config['DEFAULT']['GameHeightOffset'])
        
    def get_device_contexts(self):
        goi_dc_handle = win32gui.GetWindowDC(self.goi_hwnd)
        goi_dc = win32ui.CreateDCFromHandle(goi_dc_handle)
        mem_dc_h = gdi.CreateCompatibleDC(goi_dc_handle)
        mem_dc = win32ui.CreateDCFromHandle(mem_dc_h)
        
        self.goi_dc = goi_dc
        self.goi_dc_h = goi_dc_handle
        self.mem_dc_h = mem_dc_h
        self.mem_dc = mem_dc
        
    def get_game_window(self, debug = -1):
        mem_dc_h = self.mem_dc_h
        goi_dc = self.goi_dc
        goi_dc_h = self.goi_dc_h
        mem_dc = self.mem_dc
        
        pixel_data = POINTER(c_byte * (self.game_height * self.game_width * 3))()
        im_size = (self.game_width, self.game_height)

        dib_section = gdi.CreateDIBSection(
            goi_dc_h,
            byref(BITMAPINFOHEADER(self.game_width, self.game_height)),
            0,
            byref(pixel_data),
            None,
            0
        )
        
        gdi.SelectObject(mem_dc_h, dib_section)
        
        CAPTUREBLT = 0x40000000
        
        bitblt_success = gdi.BitBlt(
            mem_dc_h,
            0,
            0,
            self.game_width,
            self.game_height, 
            goi_dc_h,
            self.game_width_offset,
            self.game_height_offset,
            win32con.SRCCOPY | CAPTUREBLT
        )

        if debug < 0:
            return pixel_data.contents
            
        #ad hoc save screenshot to disk method
        #Note that the pixel data is originally stored as (B, G, R)
        py_data = np.zeros((self.game_height, self.game_width, 3), dtype=np.uint8)
        index = 0
        for i in range(self.game_height - 1, 0 -1, - 1):
            for j in range(self.game_width):
                for k in range(3 - 1, 0 - 1, -1):
                    py_data[i][j][k] = pixel_data.contents[index]
                    index += 1
        im = Image.fromarray(py_data.astype('uint8'), 'RGB')
        filename = self.screenshot_dir + str(debug) + ".bmp"
        im.save(filename)
        return pixel_data.contents
        
        return pixel_data_ptr
    
    def focus_window(self):
        win32gui.SetForegroundWindow(self.goi_hwnd)
        
    def cleanup(self):
        self.goi_dc.DeleteDC()
        self.mem_dc.DeleteDC()
        win32gui.ReleaseDC(self.goi_hwnd, self.goi_dc_h)
        
        
if __name__ == '__main__':
    benchmark_capture = False
    test_capture = True

    #Benchmark capture time
    if benchmark_capture:
        fetcher = WindowsScreenFetcher()
        fetcher.focus_window()
        cur_time = time.time()
        for i in range(500):
            cur_time = time.time()
            fetcher.get_game_window()
        print("Capture rate is approximately %i per second" % int(1 / ((time.time() - cur_time) / 500)))
        fetcher.cleanup()
        
    if test_capture:
        fetcher = WindowsScreenFetcher()
        fetcher.focus_window()
        for i in range(10):
            fetcher.get_game_window(i)
        fetcher.cleanup()
    

#save a few frames to test