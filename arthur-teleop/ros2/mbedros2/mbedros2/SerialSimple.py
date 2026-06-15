import serial

EOP = 'd'

def getMotorSpeed(raw_data:str) -> float:
    spd1 = 0.0
    spd2 = 0.0
    try:
        _data = raw_data.split(",")
        spd1 = float(_data[2])
        spd2 = float(_data[3])
    except :
        return 0.0, 0.0
    return spd1, spd2

class SerialSimple:
    def __init__(self, port, baudrate=9600, timeout=0.1):
        self.baudrate = baudrate
        self.port     = port

        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE
        self.bytesize = serial.EIGHTBITS
        self.timeout = timeout
        
        self.ser = None
        self.conn = False
    
    def init(self):
        self.ser = serial.Serial(port = self.port,
                            baudrate = self.baudrate,
                            parity = self.parity,
                            stopbits = self.stopbits,
                            bytesize = self.bytesize,
                            timeout = self.timeout)
    
    def start(self):
        if self.ser != None:
            self.conn = self.ser.isOpen()
            if not self.conn:
                print(f"cannot connect to {self.port}")
        else:
            print("uninitialized serial port")
        return self.conn 

    def read(self, EOP=EOP) -> str:
        _resp = b''
        try:
            self.ser.flush()
            _resp += self.ser.read_until(expected=b'\n')
        except serial.SerialException as e:
            print(e)
        return _resp.decode('utf-8')
    
    def write(self, payload:str) -> int:
        try:
            self.ser.write(payload.encode())
        except serial.SerialException as e:
            print(e)
            return -1
        return 1
    
    def close(self):
        self.ser.close()

def setMotorSpeed(ser:SerialSimple, spd1:float, spd2:float, spd3:float, spd4:float):
    ser.write(f'{spd1}/{spd2}/{spd3}/{spd4}/d')