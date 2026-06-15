import rclpy
from rclpy.node import Node

from mbedros2.SerialSimple import SerialSimple
from mbedros2.SerialSimple import getMotorSpeed
from mbedros2.SerialSimple import setMotorSpeed
import sys
import select
import tty
import termios
import time
import signal

from std_msgs.msg import Float32MultiArray

def isData():
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

old_settings = termios.tcgetattr(sys.stdin)

# Setpoint magnitude. Open-loop on the current kit, so the firmware PWM clamp
# (PWM_CAP) sets the real speed; this just selects each wheel's direction.
SPD = 10.5

# Hold-to-move: holding a key makes the terminal auto-repeat it, and each repeat
# refreshes the timer below. Releasing the key stops the repeats, so after
# HOLD_TIMEOUT with no keypress we send a stop. Must exceed the keyboard
# auto-repeat interval (raise it if a held key stutters; lower it for a snappier
# release).
HOLD_TIMEOUT = 0.4   # seconds

# Wheel order matches the firmware: s1=Motor1 front-left (FL),
# s2=Motor2 back-left (BL), s3=Motor3 back-right (BR), s4=Motor4 front-right (FR).
# Left side = s1,s2 (LEFT driver) ; Right side = s3,s4 (RIGHT driver).
def forward(ser:SerialSimple):
    setMotorSpeed(ser,  SPD,  SPD,  SPD,  SPD)

def backward(ser:SerialSimple):
    setMotorSpeed(ser, -SPD, -SPD, -SPD, -SPD)

def turnLeft(ser:SerialSimple):
    setMotorSpeed(ser, -SPD, -SPD,  SPD,  SPD)   # left rev, right fwd -> rotate CCW (turn left)

def turnRight(ser:SerialSimple):
    setMotorSpeed(ser,  SPD,  SPD, -SPD, -SPD)   # left fwd, right rev -> rotate CW (turn right)

def stop(ser:SerialSimple):
    setMotorSpeed(ser, 0.0, 0.0, 0.0, 0.0)

# Per-wheel jog for bring-up direction checks: spin ONE wheel forward, rest stopped.
def jog(ser:SerialSimple, idx:int):
    v = [0.0, 0.0, 0.0, 0.0]
    v[idx] = SPD
    setMotorSpeed(ser, v[0], v[1], v[2], v[3])

class MotorPublisher(Node):
    def __init__(self):
        super().__init__('mbedMotorCtrl')
        self.publisher = self.create_publisher(Float32MultiArray, 'motor_vel', 10)
        freq = 0.001
        self.timer = self.create_timer(freq, self.timer_callback)

        self.motor_spd1 = 0.0
        self.motor_spd2 = 0.0

    def timer_callback(self):
        motor_spd = Float32MultiArray()
        motor_spd.data = [self.motor_spd1, self.motor_spd2]
        self.publisher.publish(motor_spd)

def main(args=None):
    rclpy.init(args=args)

    motorPublisher = MotorPublisher()

    ser = SerialSimple(baudrate=115200, port='/dev/ttyACM0')
    ser.init()
    ser.start()
    stop(ser)   # known-safe state on launch — clear any setpoint left latched

    # Stop the robot if the SSH session drops (SIGHUP) or we're asked to quit
    # (SIGTERM): route both through the KeyboardInterrupt cleanup that sends a
    # final stop and restores the terminal — otherwise the firmware holds the
    # last setpoint and the robot runs away after the node dies.
    def _hangup(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGHUP, _hangup)
    signal.signal(signal.SIGTERM, _hangup)

    # Mirror throttled telemetry to a logfile so a watcher can `tail -F` it from
    # another SSH session without fighting for the serial port (only one process
    # may own /dev/ttyACM0). Truncated each run.
    telem_log = open('/tmp/ml3_drive.log', 'w', buffering=1)

    try:
        tty.setcbreak(sys.stdin.fileno())

        moving = False       # True while a drive/jog key is held down
        last_cmd_t = 0.0     # monotonic time of the most recent movement key
        last_print_t = 0.0   # monotonic time of the last telemetry print

        while ser.conn:
            resp = ser.read()
            
            motor_spd1, motor_spd2 = getMotorSpeed(resp)
            motorPublisher.motor_spd1 = motor_spd1
            motorPublisher.motor_spd2 = motor_spd2

            # Throttled telemetry (the firmware spams sp|rpm|pwm at ~1 kHz). Show
            # it on screen AND mirror to the logfile so a watcher can follow along.
            line = resp.strip()
            if line and time.monotonic() - last_print_t > 0.2:
                print(line, flush=True)
                telem_log.write(line + '\n')
                last_print_t = time.monotonic()

            if isData():
                key = sys.stdin.read(1)
                if key == 'w':
                    forward(ser)
                elif key == 's':
                    backward(ser)
                elif key == 'd':
                    turnRight(ser)
                elif key == 'a':
                    turnLeft(ser)
                elif key == 'q':
                    stop(ser)
                elif key == '1':
                    jog(ser, 0)   # Motor1 front-left  (FL)
                elif key == '2':
                    jog(ser, 1)   # Motor2 back-left   (BL)
                elif key == '3':
                    jog(ser, 2)   # Motor3 back-right  (BR)
                elif key == '4':
                    jog(ser, 3)   # Motor4 front-right (FR)

                # Any drive/jog key (re)arms the hold timer; 'q' is a hard-stop.
                if key in 'wsad1234':
                    moving = True
                    last_cmd_t = time.monotonic()
                elif key == 'q':
                    moving = False

            # Key released -> auto-repeat stops -> no key for HOLD_TIMEOUT -> stop.
            if moving and (time.monotonic() - last_cmd_t) > HOLD_TIMEOUT:
                stop(ser)
                moving = False

            rclpy.spin_once(motorPublisher)

    except KeyboardInterrupt:
        pass

    except Exception as e:
        print(e)

    # Always leave the robot stopped, even on Ctrl+C: the firmware latches the
    # last setpoint, so without this the robot keeps driving after the node dies.
    try:
        stop(ser)
    except Exception:
        pass
    telem_log.close()
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    ser.close()

    motorPublisher.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()