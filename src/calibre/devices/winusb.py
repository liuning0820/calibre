#!/usr/bin/env python2
# vim:fileencoding=utf-8
# License: GPLv3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

import os, string, _winreg as winreg, re, time, errno
from contextlib import contextmanager
from ctypes import (
    Structure, POINTER, c_ubyte, windll, byref, c_void_p, WINFUNCTYPE,
    WinError, get_last_error, sizeof, c_wchar, create_string_buffer, cast,
    wstring_at, addressof, create_unicode_buffer, string_at, c_uint64 as QWORD)
from ctypes.wintypes import DWORD, WORD, ULONG, LPCWSTR, HWND, BOOL, LPWSTR, UINT, BYTE, HANDLE

from calibre.utils.winreg.lib import Key, HKEY_LOCAL_MACHINE

# Data and function type definitions {{{

class GUID(Structure):
    _fields_ = [
        ("data1", DWORD),
        ("data2", WORD),
        ("data3", WORD),
        ("data4", c_ubyte * 8)]

    def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
        self.data1 = l
        self.data2 = w1
        self.data3 = w2
        self.data4[0] = b1
        self.data4[1] = b2
        self.data4[2] = b3
        self.data4[3] = b4
        self.data4[4] = b5
        self.data4[5] = b6
        self.data4[6] = b7
        self.data4[7] = b8

    def __str__(self):
        return "{%08x-%04x-%04x-%s-%s}" % (
            self.data1,
            self.data2,
            self.data3,
            ''.join(["%02x" % d for d in self.data4[:2]]),
            ''.join(["%02x" % d for d in self.data4[2:]]),
        )

CONFIGRET = DWORD
DEVINST = DWORD
LPDWORD = POINTER(DWORD)
LPVOID = c_void_p
REG_QWORD = 11
IOCTL_STORAGE_MEDIA_REMOVAL = 0x2D4804
IOCTL_STORAGE_EJECT_MEDIA = 0x2D4808
IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x2D1080

class STORAGE_DEVICE_NUMBER(Structure):
    _fields_ = [
        ('DeviceType', DWORD),
        ('DeviceNumber', ULONG),
        ('PartitionNumber', ULONG)
    ]

class SP_DEVINFO_DATA(Structure):
    _fields_ = [
        ('cbSize', DWORD),
        ('ClassGuid', GUID),
        ('DevInst', DEVINST),
        ('Reserved', POINTER(ULONG)),
    ]
    def __str__(self):
        return "ClassGuid:%s DevInst:%s" % (self.ClassGuid, self.DevInst)

PSP_DEVINFO_DATA = POINTER(SP_DEVINFO_DATA)

class SP_DEVICE_INTERFACE_DATA(Structure):
    _fields_ = [
        ('cbSize', DWORD),
        ('InterfaceClassGuid', GUID),
        ('Flags', DWORD),
        ('Reserved', POINTER(ULONG)),
    ]
    def __str__(self):
        return "InterfaceClassGuid:%s Flags:%s" % (self.InterfaceClassGuid, self.Flags)

ANYSIZE_ARRAY = 1

class SP_DEVICE_INTERFACE_DETAIL_DATA(Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("DevicePath", c_wchar*ANYSIZE_ARRAY)
    ]

PSP_DEVICE_INTERFACE_DETAIL_DATA = POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA)
PSP_DEVICE_INTERFACE_DATA = POINTER(SP_DEVICE_INTERFACE_DATA)
INVALID_HANDLE_VALUE = c_void_p(-1).value
GENERIC_READ = 0x80000000L
GENERIC_WRITE = 0x40000000L
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 0x3
GUID_DEVINTERFACE_VOLUME = GUID(0x53F5630D, 0xB6BF, 0x11D0, 0x94, 0xF2, 0x00, 0xA0, 0xC9, 0x1E, 0xFB, 0x8B)
GUID_DEVINTERFACE_DISK   = GUID(0x53F56307, 0xB6BF, 0x11D0, 0x94, 0xF2, 0x00, 0xA0, 0xC9, 0x1E, 0xFB, 0x8B)
GUID_DEVINTERFACE_CDROM  = GUID(0x53f56308, 0xb6bf, 0x11d0, 0x94, 0xf2, 0x00, 0xa0, 0xc9, 0x1e, 0xfb, 0x8b)
GUID_DEVINTERFACE_FLOPPY = GUID(0x53f56311, 0xb6bf, 0x11d0, 0x94, 0xf2, 0x00, 0xa0, 0xc9, 0x1e, 0xfb, 0x8b)
DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_REMOTE, DRIVE_CDROM, DRIVE_RAMDISK = 0, 1, 2, 3, 4, 5, 6
DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004
DIGCF_DEVICEINTERFACE = 0x00000010
ERROR_INSUFFICIENT_BUFFER = 0x7a
ERROR_INVALID_DATA = 0xd
HDEVINFO = HANDLE
SPDRP_DEVICEDESC = DWORD(0x00000000)
SPDRP_HARDWAREID = DWORD(0x00000001)
SPDRP_COMPATIBLEIDS = DWORD(0x00000002)
SPDRP_UNUSED0 = DWORD(0x00000003)
SPDRP_SERVICE = DWORD(0x00000004)
SPDRP_UNUSED1 = DWORD(0x00000005)
SPDRP_UNUSED2 = DWORD(0x00000006)
SPDRP_CLASS = DWORD(0x00000007)
SPDRP_CLASSGUID = DWORD(0x00000008)
SPDRP_DRIVER = DWORD(0x00000009)
SPDRP_CONFIGFLAGS = DWORD(0x0000000A)
SPDRP_MFG = DWORD(0x0000000B)
SPDRP_FRIENDLYNAME = DWORD(0x0000000C)
SPDRP_LOCATION_INFORMATION = DWORD(0x0000000D)
SPDRP_PHYSICAL_DEVICE_OBJECT_NAME = DWORD(0x0000000E)
SPDRP_CAPABILITIES = DWORD(0x0000000F)
SPDRP_UI_NUMBER = DWORD(0x00000010)
SPDRP_UPPERFILTERS = DWORD(0x00000011)
SPDRP_LOWERFILTERS = DWORD(0x00000012)
SPDRP_BUSTYPEGUID = DWORD(0x00000013)
SPDRP_LEGACYBUSTYPE = DWORD(0x00000014)
SPDRP_BUSNUMBER = DWORD(0x00000015)
SPDRP_ENUMERATOR_NAME = DWORD(0x00000016)
SPDRP_SECURITY = DWORD(0x00000017)
SPDRP_SECURITY_SDS = DWORD(0x00000018)
SPDRP_DEVTYPE = DWORD(0x00000019)
SPDRP_EXCLUSIVE = DWORD(0x0000001A)
SPDRP_CHARACTERISTICS = DWORD(0x0000001B)
SPDRP_ADDRESS = DWORD(0x0000001C)
SPDRP_UI_NUMBER_DESC_FORMAT = DWORD(0x0000001D)
SPDRP_DEVICE_POWER_DATA = DWORD(0x0000001E)
SPDRP_REMOVAL_POLICY = DWORD(0x0000001F)
SPDRP_REMOVAL_POLICY_HW_DEFAULT = DWORD(0x00000020)
SPDRP_REMOVAL_POLICY_OVERRIDE = DWORD(0x00000021)
SPDRP_INSTALL_STATE = DWORD(0x00000022)
SPDRP_LOCATION_PATHS = DWORD(0x00000023)

CR_CODES, CR_CODE_NAMES = {}, {}
for line in '''\
#define CR_SUCCESS                  			0x00000000
#define CR_DEFAULT                        0x00000001
#define CR_OUT_OF_MEMORY                  0x00000002
#define CR_INVALID_POINTER                0x00000003
#define CR_INVALID_FLAG                   0x00000004
#define CR_INVALID_DEVNODE                0x00000005
#define CR_INVALID_DEVINST          			CR_INVALID_DEVNODE
#define CR_INVALID_RES_DES                0x00000006
#define CR_INVALID_LOG_CONF               0x00000007
#define CR_INVALID_ARBITRATOR             0x00000008
#define CR_INVALID_NODELIST               0x00000009
#define CR_DEVNODE_HAS_REQS               0x0000000A
#define CR_DEVINST_HAS_REQS         			CR_DEVNODE_HAS_REQS
#define CR_INVALID_RESOURCEID             0x0000000B
#define CR_DLVXD_NOT_FOUND                0x0000000C
#define CR_NO_SUCH_DEVNODE                0x0000000D
#define CR_NO_SUCH_DEVINST          			CR_NO_SUCH_DEVNODE
#define CR_NO_MORE_LOG_CONF               0x0000000E
#define CR_NO_MORE_RES_DES                0x0000000F
#define CR_ALREADY_SUCH_DEVNODE           0x00000010
#define CR_ALREADY_SUCH_DEVINST     			CR_ALREADY_SUCH_DEVNODE
#define CR_INVALID_RANGE_LIST             0x00000011
#define CR_INVALID_RANGE                  0x00000012
#define CR_FAILURE                        0x00000013
#define CR_NO_SUCH_LOGICAL_DEV            0x00000014
#define CR_CREATE_BLOCKED                 0x00000015
#define CR_NOT_SYSTEM_VM                  0x00000016
#define CR_REMOVE_VETOED                  0x00000017
#define CR_APM_VETOED                     0x00000018
#define CR_INVALID_LOAD_TYPE              0x00000019
#define CR_BUFFER_SMALL                   0x0000001A
#define CR_NO_ARBITRATOR                  0x0000001B
#define CR_NO_REGISTRY_HANDLE             0x0000001C
#define CR_REGISTRY_ERROR                 0x0000001D
#define CR_INVALID_DEVICE_ID              0x0000001E
#define CR_INVALID_DATA                   0x0000001F
#define CR_INVALID_API                    0x00000020
#define CR_DEVLOADER_NOT_READY            0x00000021
#define CR_NEED_RESTART                   0x00000022
#define CR_NO_MORE_HW_PROFILES            0x00000023
#define CR_DEVICE_NOT_THERE               0x00000024
#define CR_NO_SUCH_VALUE                  0x00000025
#define CR_WRONG_TYPE                     0x00000026
#define CR_INVALID_PRIORITY               0x00000027
#define CR_NOT_DISABLEABLE                0x00000028
#define CR_FREE_RESOURCES                 0x00000029
#define CR_QUERY_VETOED                   0x0000002A
#define CR_CANT_SHARE_IRQ                 0x0000002B
#define CR_NO_DEPENDENT                   0x0000002C
#define CR_SAME_RESOURCES                 0x0000002D
#define CR_NO_SUCH_REGISTRY_KEY           0x0000002E
#define CR_INVALID_MACHINENAME            0x0000002F
#define CR_REMOTE_COMM_FAILURE            0x00000030
#define CR_MACHINE_UNAVAILABLE            0x00000031
#define CR_NO_CM_SERVICES                 0x00000032
#define CR_ACCESS_DENIED                  0x00000033
#define CR_CALL_NOT_IMPLEMENTED           0x00000034
#define CR_INVALID_PROPERTY               0x00000035
#define CR_DEVICE_INTERFACE_ACTIVE        0x00000036
#define CR_NO_SUCH_DEVICE_INTERFACE       0x00000037
#define CR_INVALID_REFERENCE_STRING       0x00000038
#define CR_INVALID_CONFLICT_LIST          0x00000039
#define CR_INVALID_INDEX                  0x0000003A
#define CR_INVALID_STRUCTURE_SIZE         0x0000003B'''.splitlines():
    line = line.strip()
    if line:
        name, code = line.split()[1:]
        if code.startswith('0x'):
            code = int(code, 16)
        else:
            code = CR_CODES[code]
        CR_CODES[name] = code
        CR_CODE_NAMES[code] = name

setupapi = windll.setupapi
cfgmgr = windll.CfgMgr32
kernel32 = windll.Kernel32

def cwrap(name, restype, *argtypes, **kw):
    errcheck = kw.pop('errcheck', None)
    use_last_error = bool(kw.pop('use_last_error', True))
    prototype = WINFUNCTYPE(restype, *argtypes, use_last_error=use_last_error)
    lib = cfgmgr if name.startswith('CM') else setupapi
    func = prototype((name, kw.pop('lib', lib)))
    if kw:
        raise TypeError('Unknown keyword arguments: %r' % kw)
    if errcheck is not None:
        func.errcheck = errcheck
    return func

def handle_err_check(result, func, args):
    if result == INVALID_HANDLE_VALUE:
        raise WinError(get_last_error())
    return result

def bool_err_check(result, func, args):
    if not result:
        raise WinError(get_last_error())
    return result

def config_err_check(result, func, args):
    if result != CR_CODES['CR_SUCCESS']:
        raise WindowsError((result, 'The cfgmgr32 function failed with err: %s' % CR_CODE_NAMES.get(result, result)))
    return args

GetLogicalDrives = cwrap('GetLogicalDrives', DWORD, errcheck=bool_err_check, lib=kernel32)
GetDriveType = cwrap('GetDriveTypeW', UINT, LPCWSTR, lib=kernel32)
GetVolumeNameForVolumeMountPoint = cwrap('GetVolumeNameForVolumeMountPointW', BOOL, LPCWSTR, LPWSTR, DWORD, errcheck=bool_err_check, lib=kernel32)
ExpandEnvironmentStrings = cwrap('ExpandEnvironmentStringsW', DWORD, LPCWSTR, LPWSTR, DWORD, errcheck=bool_err_check, lib=kernel32)
CreateFile = cwrap('CreateFileW', HANDLE, LPCWSTR, DWORD, DWORD, c_void_p, DWORD, DWORD, HANDLE, errcheck=handle_err_check, lib=kernel32)
DeviceIoControl = cwrap('DeviceIoControl', BOOL, HANDLE, DWORD, LPVOID, DWORD, LPVOID, DWORD, POINTER(DWORD), LPVOID, errcheck=bool_err_check, lib=kernel32)
CloseHandle = cwrap('CloseHandle', BOOL, HANDLE, errcheck=bool_err_check, lib=kernel32)
QueryDosDevice = cwrap('QueryDosDeviceW', DWORD, LPCWSTR, LPWSTR, DWORD, errcheck=bool_err_check, lib=kernel32)

SetupDiGetClassDevs = cwrap('SetupDiGetClassDevsW', HDEVINFO, POINTER(GUID), LPCWSTR, HWND, DWORD, errcheck=handle_err_check)
SetupDiEnumDeviceInterfaces = cwrap('SetupDiEnumDeviceInterfaces', BOOL, HDEVINFO, PSP_DEVINFO_DATA, POINTER(GUID), DWORD, PSP_DEVICE_INTERFACE_DATA)
SetupDiDestroyDeviceInfoList = cwrap('SetupDiDestroyDeviceInfoList', BOOL, HDEVINFO, errcheck=bool_err_check)
SetupDiGetDeviceInterfaceDetail = cwrap(
    'SetupDiGetDeviceInterfaceDetailW', BOOL, HDEVINFO, PSP_DEVICE_INTERFACE_DATA, PSP_DEVICE_INTERFACE_DETAIL_DATA, DWORD, POINTER(DWORD), PSP_DEVINFO_DATA)
SetupDiEnumDeviceInfo = cwrap('SetupDiEnumDeviceInfo', BOOL, HDEVINFO, DWORD, PSP_DEVINFO_DATA)
SetupDiGetDeviceRegistryProperty = cwrap(
    'SetupDiGetDeviceRegistryPropertyW', BOOL, HDEVINFO, PSP_DEVINFO_DATA, DWORD, POINTER(DWORD), POINTER(BYTE), DWORD, POINTER(DWORD))

CM_Get_Parent = cwrap('CM_Get_Parent', CONFIGRET, POINTER(DEVINST), DEVINST, ULONG, errcheck=config_err_check)
CM_Get_Device_ID_Size = cwrap('CM_Get_Device_ID_Size', CONFIGRET, POINTER(ULONG), DEVINST, ULONG)
CM_Get_Device_ID = cwrap('CM_Get_Device_IDW', CONFIGRET, DEVINST, LPWSTR, ULONG, ULONG)
CM_Request_Device_Eject = cwrap('CM_Request_Device_EjectW', CONFIGRET, DEVINST, c_void_p, LPWSTR, ULONG, ULONG, errcheck=config_err_check)
# }}}

# Utility functions {{{
@contextmanager
def get_device_set(guid=byref(GUID_DEVINTERFACE_VOLUME), enumerator=None, flags=DIGCF_PRESENT | DIGCF_DEVICEINTERFACE):
    dev_list = SetupDiGetClassDevs(guid, enumerator, None, flags)
    yield dev_list
    SetupDiDestroyDeviceInfoList(dev_list)

def get_all_removable_drives():
    mask = GetLogicalDrives()
    ans = {}
    buf = create_unicode_buffer(100)
    for drive_letter in string.ascii_uppercase:
        drive_present = bool(mask & 0b1)
        mask >>= 1
        drive_root = drive_letter + ':' + os.sep
        if drive_present and GetDriveType(drive_root) == DRIVE_REMOVABLE:  # Removable, present drive
            try:
                GetVolumeNameForVolumeMountPoint(drive_root, buf, len(buf))
            except WindowsError:
                continue
            ans[buf.value] = drive_letter
    return ans

def get_device_id(devinst, buf=None):
    if buf is None:
        buf = create_unicode_buffer(512)
    while True:
        ret = CM_Get_Device_ID(devinst, buf, len(buf), 0)
        if ret == CR_CODES['CR_BUFFER_SMALL']:
            devid_size = ULONG(0)
            CM_Get_Device_ID_Size(byref(devid_size), devinst, 0)
            buf = create_unicode_buffer(devid_size.value)
            continue
        if ret != CR_CODES['CR_SUCCESS']:
            raise WindowsError((result, 'The cfgmgr32 function failed with err: %s' % CR_CODE_NAMES.get(result, result)))
        break
    return wstring_at(buf), buf

def expand_environment_strings(src):
    sz = ExpandEnvironmentStrings(src, None, 0)
    while True:
        buf = create_unicode_buffer(sz)
        nsz = ExpandEnvironmentStrings(src, buf, len(buf))
        if nsz <= sz:
            return buf.value
        sz = nsz

def convert_registry_data(raw, size, dtype):
    if dtype == winreg.REG_NONE:
        return None
    if dtype == winreg.REG_BINARY:
        return string_at(raw, size)
    if dtype in (winreg.REG_SZ, winreg.REG_EXPAND_SZ, winreg.REG_MULTI_SZ):
        ans = wstring_at(raw, size // 2).rstrip('\0')
        if dtype == winreg.REG_MULTI_SZ:
            ans = tuple(ans.split('\0'))
        elif dtype == winreg.REG_EXPAND_SZ:
            ans = expand_environment_strings(ans)
        return ans
    if dtype == winreg.REG_DWORD:
        if size == 0:
            return 0
        return cast(raw, LPDWORD).contents.value
    if dtype == REG_QWORD:
        if size == 0:
            return 0
        return cast(raw, POINTER(QWORD)).contents.value
    raise ValueError('Unsupported data type: %r' % dtype)

def get_device_registry_property(dev_list, p_devinfo, property_type=SPDRP_HARDWAREID, buf=None):
    if buf is None:
        buf = create_string_buffer(1024)
    data_type = DWORD(0)
    required_size = DWORD(0)
    ans = None
    while True:
        if not SetupDiGetDeviceRegistryProperty(dev_list, p_devinfo, property_type, byref(data_type), cast(buf, POINTER(BYTE)), len(buf), byref(required_size)):
            err = get_last_error()
            if err == ERROR_INSUFFICIENT_BUFFER:
                buf = create_string_buffer(required_size)
                continue
            if err == ERROR_INVALID_DATA:
                break
            raise WinError(err)
        ans = convert_registry_data(buf, required_size.value, data_type.value)
        break
    return buf, ans

def get_device_interface_detail_data(dev_list, p_interface_data, buf=None):
    if buf is None:
        buf = create_string_buffer(512)
    detail = cast(buf, PSP_DEVICE_INTERFACE_DETAIL_DATA)
    detail.contents.cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA)
    required_size = DWORD(0)
    devinfo = SP_DEVINFO_DATA()
    devinfo.cbSize = sizeof(devinfo)
    while True:
        if not SetupDiGetDeviceInterfaceDetail(dev_list, p_interface_data, detail, len(buf), byref(required_size), byref(devinfo)):
            err = get_last_error()
            if err == ERROR_INSUFFICIENT_BUFFER:
                buf = create_string_buffer(required_size + 50)
                detail = cast(buf, PSP_DEVICE_INTERFACE_DETAIL_DATA)
                detail.contents.cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA)
                continue
            raise WinError(err)
        break
    return buf, devinfo, wstring_at(addressof(buf) + sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA._fields_[0][1]))

# }}}

# get_removable_drives() {{{

class NoRemovableDrives(WindowsError):
    pass

def get_removable_drives(debug=False):
    drive_map = get_all_removable_drives()
    if not drive_map:
        raise NoRemovableDrives('No removable drives found!')

    buf = None
    pbuf = create_unicode_buffer(512)
    ans = {}
    with get_device_set() as dev_list:
        interface_data = SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)
        i = -1
        while True:
            i += 1
            if not SetupDiEnumDeviceInterfaces(dev_list, None, byref(GUID_DEVINTERFACE_VOLUME), i, byref(interface_data)):
                break
            buf, devinfo, devpath = get_device_interface_detail_data(dev_list, byref(interface_data), buf)
            candidates = []
            # Get the devpaths for all parents of this device. This is not
            # actually necessary on Vista+, so we simply ignore any windows API
            # failures.
            parent = DEVINST(devinfo.DevInst)
            while True:
                try:
                    CM_Get_Parent(byref(parent), parent, 0)
                except WindowsError:
                    break
                try:
                    devid, pbuf = get_device_id(parent, buf=pbuf)
                except WindowsError:
                    break
                candidates.append(devid)
            candidates.append(devpath)

            if not devpath.endswith(os.sep):
                devpath += os.sep
            try:
                GetVolumeNameForVolumeMountPoint(devpath, pbuf, len(pbuf))
            except WindowsError:
                continue
            drive_letter = drive_map.get(pbuf.value)
            if drive_letter is not None:
                ans[drive_letter] = candidates
        return ans
# }}}

# get_drive_letters_for_device() {{{

_devid_pat = None
def devid_pat():
    global _devid_pat
    if _devid_pat is None:
        _devid_pat = re.compile(r'VID_([a-f0-9]{4})&PID_([a-f0-9]{4})&REV_([a-f0-9]{4})', re.I)
    return _devid_pat


def get_drive_letters_for_device(vendor_id, product_id, debug=False):
    rbuf = buf = wbuf = None
    ans = []

    # First search for a device matching the specified USB ids
    with get_device_set(enumerator='USB', flags=DIGCF_PRESENT | DIGCF_ALLCLASSES) as dev_list:
        devinfo = SP_DEVINFO_DATA()
        devinfo.cbSize = sizeof(SP_DEVINFO_DATA)
        i = -1
        found_at = None
        while True:
            i += 1
            if not SetupDiEnumDeviceInfo(dev_list, i, byref(devinfo)):
                break
            rbuf, devid = get_device_registry_property(dev_list, byref(devinfo), buf=rbuf)
            if devid:
                m = devid_pat().search(devid[0])
                if m is None:
                    continue
                try:
                    vid, pid, rev = map(lambda x:int(x, 16), m.group(1, 2, 3))
                except Exception:
                    continue
                if vid == vendor_id and pid == product_id:
                    found_at = i - 1
                    break
    if found_at is None:
        return ans
    try:
        with Key(open_at='SYSTEM\\CurrentControlSet\\Enum\\USB\\VID_%04X&PID_%04X' % (vid, pid), root=HKEY_LOCAL_MACHINE) as key:
            available_uuids = {uuid.lower() for uuid in key.iterkeynames()}
    except WindowsError as err:
        if err.errno != errno.ENOENT:
            raise
        return ans
    if not available_uuids:
        return ans
    with get_device_set() as dev_list:
        interface_data = SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)
        i = -1
        drive_map = get_all_removable_drives()
        vbuf = create_unicode_buffer(100)
        while True:
            i += 1
            if not SetupDiEnumDeviceInterfaces(dev_list, None, byref(GUID_DEVINTERFACE_VOLUME), i, byref(interface_data)):
                break
            buf, devinfo, devpath = get_device_interface_detail_data(dev_list, byref(interface_data), buf)
            devid, wbuf = get_device_id(devinfo.DevInst, buf=wbuf)
            if 'USBSTOR' not in devid:
                continue
            parts = devid.split('#')
            if len(parts) < 3:
                continue
            uuid = parts[2].partition('&')[0].lower()
            if uuid not in available_uuids:
                continue
            if not devpath.endswith(os.sep):
                devpath += os.sep
            try:
                GetVolumeNameForVolumeMountPoint(devpath, vbuf, len(vbuf))
            except WindowsError:
                continue
            drive_letter = drive_map.get(vbuf.value)
            if drive_letter is not None:
                ans.append(drive_letter)
        return ans
# }}}

def get_usb_devices():  # {{{
    buf = None
    ans = []
    with get_device_set(guid=None, enumerator='USB', flags=DIGCF_PRESENT | DIGCF_ALLCLASSES) as dev_list:
        devinfo = SP_DEVINFO_DATA()
        devinfo.cbSize = sizeof(SP_DEVINFO_DATA)
        i = -1
        while True:
            i += 1
            if not SetupDiEnumDeviceInfo(dev_list, i, byref(devinfo)):
                break
            buf, devid = get_device_registry_property(dev_list, byref(devinfo), buf=buf)
            if devid:
                ans.append(devid[0].lower())
    return ans
# }}}

def is_usb_device_connected(vendor_id, product_id):  # {{{
    buf = None
    with get_device_set(guid=None, enumerator='USB', flags=DIGCF_PRESENT | DIGCF_ALLCLASSES) as dev_list:
        devinfo = SP_DEVINFO_DATA()
        devinfo.cbSize = sizeof(SP_DEVINFO_DATA)
        i = -1
        while True:
            i += 1
            if not SetupDiEnumDeviceInfo(dev_list, i, byref(devinfo)):
                break
            buf, devid = get_device_registry_property(dev_list, byref(devinfo), buf=buf)
            if devid:
                m = devid_pat().search(devid[0])
                if m is not None:
                    try:
                        vid, pid = map(lambda x: int(x, 16), m.group(1, 2))
                    except Exception:
                        continue
                    if vid == vendor_id and pid == product_id:
                        return True
    return False
# }}}

def eject_drive(drive_letter):  # {{{
    drive_letter = type('')(drive_letter)[0]
    volume_access_path = '\\\\.\\' + drive_letter + ':'
    sdn = STORAGE_DEVICE_NUMBER()
    handle = CreateFile(volume_access_path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    try:
        DeviceIoControl(handle, IOCTL_STORAGE_GET_DEVICE_NUMBER, None, 0, byref(sdn), sizeof(STORAGE_DEVICE_NUMBER), None, None)
    finally:
        CloseHandle(handle)
    devinst = devinst_from_device_number(drive_letter, sdn.DeviceNumber)
    if devinst is None:
        raise ValueError('Could not find device instance number from drive letter: %s' % drive_letter)
    parent = DEVINST(0)
    CM_Get_Parent(byref(parent), devinst, 0)
    max_tries = 3
    while max_tries >= 0:
        max_tries -= 1
        try:
            CM_Request_Device_Eject(parent, None, None, 0, 0)
        except WindowsError:
            time.sleep(0.5)
            continue
        return
    raise ValueError('Failed to eject drive %s after three tries' % drive_letter)

def devinst_from_device_number(drive_letter, device_number):
    drive_root = drive_letter + ':' + os.sep
    buf = create_unicode_buffer(512)
    bbuf = None
    sdn = STORAGE_DEVICE_NUMBER()
    drive_type = GetDriveType(drive_root)
    QueryDosDevice(drive_letter + ':', buf, len(buf))
    is_floppy = '\\floppy' in buf.value.lower()
    if drive_type == DRIVE_REMOVABLE:
        guid = GUID_DEVINTERFACE_FLOPPY if is_floppy else GUID_DEVINTERFACE_DISK
    elif drive_type == DRIVE_FIXED:
        guid = GUID_DEVINTERFACE_DISK
    elif drive_type == DRIVE_CDROM:
        guid = GUID_DEVINTERFACE_CDROM
    else:
        raise ValueError('Unknown drive_type: %d' % drive_type)
    with get_device_set(guid=guid) as dev_list:
        interface_data = SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)
        i = -1
        while True:
            i += 1
            if not SetupDiEnumDeviceInterfaces(dev_list, None, byref(guid), i, byref(interface_data)):
                break
            try:
                bbuf, devinfo, devpath = get_device_interface_detail_data(dev_list, byref(interface_data), bbuf)
            except WindowsError:
                continue
            handle = CreateFile(devpath, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
            try:
                DeviceIoControl(handle, IOCTL_STORAGE_GET_DEVICE_NUMBER, None, 0, byref(sdn), sizeof(STORAGE_DEVICE_NUMBER), None, None)
            finally:
                CloseHandle(handle)
            if sdn.DeviceNumber == device_number:
                return devinfo.DevInst
# }}}

if __name__ == '__main__':
    from pprint import pprint
    pprint(get_usb_devices())
    print('Is connected:', is_usb_device_connected(0x1949, 0x4))
    pprint(get_all_removable_drives())
    pprint(get_removable_drives())
    pprint(get_drive_letters_for_device(0x1949, 0x4))
    eject_drive('E')