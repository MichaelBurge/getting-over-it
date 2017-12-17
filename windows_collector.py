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
import win32api
import ctypes
import sys

config = ConfigParser()
config.read('win_capture_config.ini')
if config['DEFAULT']['Configed'] == 'False':
    raise Exception('Please confirm the settings in config and then set Configed to True')
    
gdi_path = config['DEFAULT']['WinGDIPath']
gdi = ctypes.WinDLL(gdi_path)

LONG = ctypes.c_long
DWORD = ctypes.c_ulong
ULONG_PTR = ctypes.POINTER(DWORD)
WORD = ctypes.c_ushort

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

#mouseData, time and dwExtraInfo should be zero for us
class MOUSEINPUT(ctypes.Structure):
    _fields_ = (('dx', LONG),
                ('dy', LONG),
                ('mouseData', DWORD),
                ('dwFlags', DWORD),
                ('time', DWORD),
                ('dwExtraInfo', ULONG_PTR))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (('wVk', WORD),
                ('wScan', WORD),
                ('dwFlags', DWORD),
                ('time', DWORD),
                ('dwExtraInfo', ULONG_PTR))


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (('uMsg', DWORD),
                ('wParamL', WORD),
                ('wParamH', WORD))


class _INPUTunion(ctypes.Union):
    _fields_ = (('mi', MOUSEINPUT),
                ('ki', KEYBDINPUT),
                ('hi', HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (('type', DWORD),
                ('union', _INPUTunion))

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


        
class FrameDeltaer():
    def __init__(self, pid):
        self.pid = pid
        self.changing_address = 0x1C4E070
        self.cached_value = None

    def read_process_memory(self, address, size, allow_partial=False):
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        ERROR_PARTIAL_COPY = 0x012B
        PROCESS_VM_READ = 0x0010
        
        buf = (ctypes.c_char * size)()
        nread = ctypes.c_size_t()
        hProcess = kernel32.OpenProcess(PROCESS_VM_READ, False, self.pid)
        try:
            kernel32.ReadProcessMemory(hProcess, address, buf, size,
                ctypes.byref(nread))
        except WindowsError as e:
            if not allow_partial or e.winerror != ERROR_PARTIAL_COPY:
                raise
        finally:
            kernel32.CloseHandle(hProcess)
        return buf[:nread.value]
            
    def is_new_frame(self):
        new_value = int.from_bytes(self.read_process_memory(self.changing_address, 4), byteorder='little', signed=False)
        if self.cached_value == new_value:
            return False
        self.cached_value = new_value
        return True
        
    def fetch_moving_address(self):
        return int.from_bytes(self.read_process_memory(self.changing_address, 4), byteorder='little', signed=False)
        
class WindowsScreenFetcher:
    def __init__(self):
        self.parse_config()
        self.goi_hwnd = self.get_game_window_handle()
        self.get_device_contexts()
        self.frame_deltaer = FrameDeltaer(self.get_pid())
       
    def get_pid(self):
        thread_id, pid = win32process.GetWindowThreadProcessId(self.goi_hwnd)
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
        
    def send_inputs(self, inputs):
        nInputs = len(inputs)
        LPINPUT = INPUT * nInputs
        pInputs = LPINPUT(*inputs)
        cbSize = ctypes.c_int(ctypes.sizeof(INPUT))
        return ctypes.windll.user32.SendInput(nInputs, pInputs, cbSize)   
        
    def move_mouse(self, dx, dy):
        long_x = LONG(x)
        long_y = LONG(y)
        mouse_move_event = [INPUT(INPUT_MOUSE, _INPUTunion(mi = MOUSEINPUT(long_x, long_y, 0, MOUSEEVENTF_MOVE, 0, None)))]
        self.send_inputs(mouse_move_event)
        
if __name__ == '__main__':
    benchmark_capture = False
    test_capture = False
    test_mouse = False
    test_frame_deltaer = False
    
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
    
    if test_mouse:
        fetcher = WindowsScreenFetcher()
        fetcher.focus_window()
        for i in range(100):
            time.sleep(0.1)
            x = random.randint(-100, 100)
            y = random.randint(-100, 100)
            fetcher.move_mouse(x, y)
        fetcher.cleanup()
    
    if test_frame_deltaer:
        fetcher = WindowsScreenFetcher()
        fetcher.focus_window()
        i = 0
        j = 0
        cur_time = time.time()
        while i < 600:
            is_new = fetcher.frame_deltaer.is_new_frame()
            if is_new:
                i += 1
            j += 1
        print("Game runs at approximately %i frames per second, sampling at %i per second" % (int(1 / ((time.time() - cur_time) / 600)), int(1 / ((time.time() - cur_time) / j))))
#save a few frames to test