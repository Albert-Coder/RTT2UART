import sys
from PySide2.QtWidgets import QApplication, QMainWindow, QDialog, QHeaderView, QAbstractItemView, QMessageBox, QSystemTrayIcon, QMenu, QAction, qApp
from PySide2.QtCore import QFile, QAbstractTableModel
from PySide2 import QtGui
from PySide2 import QtCore
from PySide2.QtGui import QFont, QIcon
from PySide2.QtNetwork import QLocalSocket, QLocalServer
from ui_rtt2uart import Ui_dialog
from ui_sel_device import Ui_Dialog

import serial.tools.list_ports
import serial
import ctypes.util as ctypes_util
import xml.etree.ElementTree as ET
import pylink
from rtt2uart import rtt_to_serial
import logging
import pickle
import os

logging.basicConfig(level=logging.NOTSET,
                    format='%(asctime)s - [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s')
logger = logging.getLogger(__name__)

# pylink支持的最大速率是12000kHz（Segger RTT Viewer额外可选 15000, 20000, 25000, 30000, 40000, 50000）
speed_list = [5, 10, 20, 30, 50, 100, 200, 300, 400, 500, 600, 750,
              900, 1000, 1334, 1600, 2000, 2667, 3200, 4000, 4800, 5334, 6000, 8000, 9600, 12000]

baudrate_list = [50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800,
                 9600, 19200, 38400, 57600, 115200, 230400, 460800, 500000, 576000, 921600]


def resource_path(relative_path):
    '''返回资源绝对路径'''
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller会创建临时文件夹temp
        # 并把路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath('.')

    return os.path.join(base_path, relative_path)


class DeviceTableModel(QtCore.QAbstractTableModel):
    def __init__(self, deice_list, header):
        super(DeviceTableModel, self).__init__()

        self.mylist = deice_list
        self.header = header

    def rowCount(self, parent):
        return len(self.mylist)

    def columnCount(self, parent):
        return len(self.header)

    def data(self, index, role):
        if not index.isValid():
            return None
        elif role != QtCore.Qt.DisplayRole:
            return None

        return self.mylist[index.row()][index.column()]

        return None

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None


class DeviceSeleteDialog(QDialog):
    def __init__(self):
        super(DeviceSeleteDialog, self).__init__()
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        self.setWindowIcon(QIcon(resource_path(r'swap_horiz_16px.ico')))

        self._target = None

        filepath = self.get_jlink_devices_list_file()
        if filepath != '':
            self.devices_list = self.parse_jlink_devices_list_file(filepath)

        if len(self.devices_list):

            # 从headdata中取出数据，放入到模型中
            headdata = ["Manufacturer", "Device", "Core",
                        "NumCores", "Flash Size", "RAM Size"]

            # 生成一个模型，用来给tableview
            model = DeviceTableModel(self.devices_list, headdata)

            self.ui.tableView.setModel(model)
            # set font
            # font = QFont("Courier New", 9)
            # self.ui.tableView.setFont(font)
            # set column width to fit contents (set font first!)
            self.ui.tableView.resizeColumnsToContents()
            self.ui.tableView.resizeRowsToContents()
            self.ui.tableView.setSelectionBehavior(
                QAbstractItemView.SelectRows)

            self.ui.tableView.clicked.connect(self.reflash_selete_device)

    def get_jlink_devices_list_file(self):
        '''
        lib_jlink = pylink.Library()

        path = ctypes_util.find_library(lib_jlink._sdk)

        if path is None:
            # Couldn't find it the standard way.  Fallback to the non-standard
            # way of finding the J-Link library.  These methods are operating
            # system specific.
            if lib_jlink._windows or lib_jlink._cygwin:
                path = next(lib_jlink.find_library_windows(), None)
            elif sys.platform.startswith('linux'):
                path = next(lib_jlink.find_library_linux(), None)
            elif sys.platform.startswith('darwin'):
                path = next(lib_jlink.find_library_darwin(), None)

            if path is not None:
                path = path.replace(
                    lib_jlink.get_appropriate_windows_sdk_name()+".dll", "JLinkDevices.xml")
            else:
                path = ''
        else:
            path = ''
        '''
        if os.path.exists(r'JLinkDevicesBuildIn.xml') == True:
            return os.path.abspath('JLinkDevicesBuildIn.xml')
        else:
            raise Exception("Can not find device database !")

    def parse_jlink_devices_list_file(self, path):
        parsefile = open(path, 'r')

        tree = ET.ElementTree(file=parsefile)

        jlink_devices_list = []

        for VendorInfo in tree.findall('VendorInfo'):
            for DeviceInfo in VendorInfo.findall('DeviceInfo'):
                device_item = []

                # get Manufacturer
                device_item.append(VendorInfo.attrib['Name'])
                # get Device
                device_item.append(DeviceInfo.attrib['Name'])
                # get Core
                device_item.append(DeviceInfo.attrib['Core'])
                # get NumCores
                # now fix 1
                device_item.append('1')
                # get Flash Size
                flash_size = 0
                for FlashBankInfo in DeviceInfo.findall('FlashBankInfo'):
                    flash_size += int(FlashBankInfo.attrib['Size'], 16)

                flash_size = flash_size // 1024
                if flash_size < 1024:
                    device_item.append(str(flash_size)+' KB')
                else:
                    flash_size = flash_size // 1024
                    device_item.append(str(flash_size)+' MB')
                # get RAM Size
                ram_size = 0
                if 'WorkRAMSize' in DeviceInfo.attrib.keys():
                    ram_size += int(DeviceInfo.attrib['WorkRAMSize'], 16)

                device_item.append(str(ram_size//1024)+' KB')

                # add item to list
                jlink_devices_list.append(device_item)

        parsefile.close()

        return jlink_devices_list

    def reflash_selete_device(self):
        index = self.ui.tableView.currentIndex()
        self._target = self.devices_list[index.row()][1]
        self.ui.label_sel_dev.setText(self._target)

    def get_target_device(self):
        return self._target


class MainWindow(QDialog):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.ui = Ui_dialog()
        self.ui.setupUi(self)

        self.setWindowIcon(QIcon(resource_path(r'swap_horiz_16px.ico')))

        self.setting_file_path = os.path.join(os.getcwd(), "settings")

        self.start_state = False
        self.target_device = None
        self.rtt2uart = None

        self.ui.comboBox_Interface.addItem("JTAG")
        self.ui.comboBox_Interface.addItem("SWD")
        self.ui.comboBox_Interface.addItem("cJTAG")
        self.ui.comboBox_Interface.addItem("FINE")

        for i in range(len(speed_list)):
            self.ui.comboBox_Speed.addItem(str(speed_list[i]) + " kHz")

        for i in range(len(baudrate_list)):
            self.ui.comboBox_baudrate.addItem(str(baudrate_list[i]))

        self.port_scan()

        self.settings = {'device': [], 'device_index': 0, 'interface': 0,
                         'speed': 0, 'port': 0, 'buadrate': 0}

        # 检查是否存在上次配置，存在则加载
        if os.path.exists(self.setting_file_path) == True:
            with open(self.setting_file_path, 'rb') as f:
                self.settings = pickle.load(f)

            f.close()

            # 应用上次配置
            if len(self.settings['device']):
                self.ui.comboBox_Device.addItems(self.settings['device'])
                self.target_device = self.settings['device'][self.settings['device_index']]
            self.ui.comboBox_Device.setCurrentIndex(
                self.settings['device_index'])
            self.ui.comboBox_Interface.setCurrentIndex(
                self.settings['interface'])
            self.ui.comboBox_Speed.setCurrentIndex(self.settings['speed'])
            self.ui.comboBox_Port.setCurrentIndex(self.settings['port'])
            self.ui.comboBox_baudrate.setCurrentIndex(
                self.settings['buadrate'])
        else:
            logger.info('Setting file not exist', exc_info=True)
            self.ui.comboBox_Interface.setCurrentIndex(1)
            self.settings['interface'] = 1
            self.ui.comboBox_Speed.setCurrentIndex(19)
            self.settings['speed'] = 19
            self.ui.comboBox_baudrate.setCurrentIndex(16)
            self.settings['buadrate'] = 16

        # 信号-槽
        self.ui.pushButton_Start.clicked.connect(self.start)
        self.ui.pushButton_scan.clicked.connect(self.port_scan)
        self.ui.pushButton_Selete_Device.clicked.connect(
            self.target_device_selete)
        self.ui.comboBox_Device.currentIndexChanged.connect(
            self.device_change_slot)
        self.ui.comboBox_Interface.currentIndexChanged.connect(
            self.interface_change_slot)
        self.ui.comboBox_Speed.currentIndexChanged.connect(
            self.speed_change_slot)
        self.ui.comboBox_Port.currentIndexChanged.connect(
            self.port_change_slot)
        self.ui.comboBox_baudrate.currentIndexChanged.connect(
            self.buadrate_change_slot)

    def closeEvent(self, e):
        if self.rtt2uart is not None and self.start_state == True:
            self.rtt2uart.stop()

        # 保存当前配置
        with open(self.setting_file_path, 'wb') as f:
            pickle.dump(self.settings, f)

        f.close()

        e.accept()

    def port_scan(self):
        port_list = list(serial.tools.list_ports.comports())
        self.ui.comboBox_Port.clear()
        port_list.sort()
        for port in port_list:
            try:
                s = serial.Serial(port[0])
                s.close()
                self.ui.comboBox_Port.addItem(port[0])
            except (OSError, serial.SerialException):
                pass

    def start(self):
        if self.start_state == False:
            try:
                if self.target_device is not None:

                    selete_interface = self.ui.comboBox_Interface.currentText()
                    if (selete_interface == 'JTAG'):
                        device_interface = pylink.enums.JLinkInterfaces.JTAG
                    elif (selete_interface == 'SWD'):
                        device_interface = pylink.enums.JLinkInterfaces.SWD
                    elif (selete_interface == 'cJTAG'):
                        device_interface = None
                    elif (selete_interface == 'FINE'):
                        device_interface = pylink.enums.JLinkInterfaces.FINE

                    self.rtt2uart = rtt_to_serial(self.target_device, self.ui.comboBox_Port.currentText(
                    ), self.ui.comboBox_baudrate.currentText(), device_interface, speed_list[self.ui.comboBox_Speed.currentIndex()], self.ui.checkBox_resettarget.isChecked())

                    self.rtt2uart.start()

                    # 启动后不能再进行配置
                    self.ui.comboBox_Device.setEnabled(False)
                    self.ui.pushButton_Selete_Device.setEnabled(False)
                    self.ui.comboBox_Interface.setEnabled(False)
                    self.ui.comboBox_Speed.setEnabled(False)
                    self.ui.comboBox_Port.setEnabled(False)
                    self.ui.comboBox_baudrate.setEnabled(False)
                    self.ui.pushButton_scan.setEnabled(False)
                else:
                    raise Exception("Please selete the target device !")

            except Exception as errors:
                QMessageBox.critical(self, "Errors", str(errors))
            else:
                self.start_state = True
                self.ui.pushButton_Start.setText("Stop")
        else:
            try:
                # 停止后才能再次配置
                self.ui.comboBox_Device.setEnabled(True)
                self.ui.pushButton_Selete_Device.setEnabled(True)
                self.ui.comboBox_Interface.setEnabled(True)
                self.ui.comboBox_Speed.setEnabled(True)
                self.ui.comboBox_Port.setEnabled(True)
                self.ui.comboBox_baudrate.setEnabled(True)
                self.ui.pushButton_scan.setEnabled(True)

                self.rtt2uart.stop()

                self.start_state = False
                self.ui.pushButton_Start.setText("Start")
            except:
                logger.error('Stop rtt2uart failed', exc_info=True)
                pass

    def target_device_selete(self):
        device_ui = DeviceSeleteDialog()
        device_ui.exec_()
        self.target_device = device_ui.get_target_device()

        if self.target_device not in self.settings['device']:
            self.settings['device'].append(self.target_device)
            self.ui.comboBox_Device.addItem(self.target_device)
            self.ui.comboBox_Device.setCurrentIndex(
                len(self.settings['device']) - 1)

    def device_change_slot(self, index):
        self.settings['device_index'] = index
        self.target_device = self.ui.comboBox_Device.currentText()

    def interface_change_slot(self, index):
        self.settings['interface'] = index

    def speed_change_slot(self, index):
        self.settings['speed'] = index

    def port_change_slot(self, index):
        self.settings['port'] = index

    def buadrate_change_slot(self, index):
        self.settings['buadrate'] = index


# class MyTray(QSystemTrayIcon):

#     def __init__(self):
#         super().__init__()
#         self.setIcon(QIcon(r'swap_horiz_16px.ico'))  # 设置系统托盘图标
#         self.setToolTip('RTT2UART')
#         self.activated.connect(self.act)  # 设置托盘点击事件处理函数
#         self.tray_menu = QMenu(QApplication.desktop())  # 创建菜单
#         self.ShowAction = QAction('&show')  # 添加一级菜单动作选项(还原主窗口)
#         self.QuitAction = QAction('&exit')  # 添加一级菜单动作选项(退出程序)
#         self.ShowAction.triggered.connect(window.show)
#         self.QuitAction.triggered.connect(qApp.quit)
#         self.QuitAction.setToolTip('Exit the software')
#         self.ShowAction.setToolTip('show the window')
#         self.tray_menu.addAction(self.ShowAction)  # 为菜单添加动作
#         self.tray_menu.addAction(self.QuitAction)
#         self.setContextMenu(self.tray_menu)  # 设置系统托盘菜单

#     def act(self, reason):
#         if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:  # 单击或双击
#             window.showNormal()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    serverName = 'myuniqueservername'
    lsocket = QLocalSocket()
    lsocket.connectToServer(serverName)

    # 如果连接成功，表明server已经存在，当前已有实例在运行
    if lsocket.waitForConnected(200) == False:

        # 没有实例运行，创建服务器
        localServer = QLocalServer()
        localServer.listen(serverName)

        try:
            window = MainWindow()
            window.setWindowTitle("RTT2UART Control Panel V1.3.0")
            window.show()

            # window.hide()
            # mytray = MyTray()
            # mytray.show()

            sys.exit(app.exec_())
        finally:
            localServer.close()
