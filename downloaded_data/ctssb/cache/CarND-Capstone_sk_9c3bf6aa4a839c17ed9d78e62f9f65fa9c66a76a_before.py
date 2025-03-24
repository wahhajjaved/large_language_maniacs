from pid import PID
from yaw_controller import YawController
from lowpass import LowPassFilter

GAS_DENSITY = 2.858
ONE_MPH = 0.44704


class Controller(object):
    def __init__(self, *args, **kwargs):
        vehicle_mass = args[0]
        fuel_capacity = args[1]
        wheel_radius = args[2]
        self.decel_limit = args[3]
        accel_limit = args[4]
        max_steer_angle = args[5]
        wheel_base = args[6]
        steer_ratio = args[7]
        max_lat_accel = args[8]
        self._sample_time = 1/args[9]  # 1/loop rate

        self.r = wheel_radius
        self.mass = (vehicle_mass + fuel_capacity*GAS_DENSITY)

        v_kp = 0.4
        v_ki = 0.000
        v_kd = 0.2
        self.vel_pid = PID(kp=v_kp, ki=v_ki, kd=v_kd, mn=self.decel_limit, mx=accel_limit)  # speed controller

        self._yaw_controller = YawController(wheel_base=wheel_base, steer_ratio=steer_ratio, min_speed=10,
                                             max_lat_accel=max_lat_accel, max_steer_angle=max_steer_angle)

        self.lpf_steering = LowPassFilter(tau=2, ts=5)
        pass

    def control(self, *args, **kwargs):
        proposed_lin_vel = args[0]
        proposed_ang_vel = args[1]
        current_lin_vel = args[2]

        steering_angle = self._yaw_controller.get_steering(linear_velocity=proposed_lin_vel,
                                                           angular_velocity=proposed_ang_vel,
                                                           current_velocity=current_lin_vel)
        final_steering_angle = self.lpf_steering.filt(steering_angle)

        throttle = 0
        brake = 0
        vel_error = proposed_lin_vel - current_lin_vel
        vel_cmd = self.vel_pid.step(vel_error, self._sample_time)
        if vel_cmd > 0.5:
            # TODO maybe use low pass filter?
            throttle = min(1, vel_cmd)
            brake = 0
        elif vel_cmd < 0:
            throttle = 0
            brake = self.mass * abs(vel_cmd) * self.r

        # Return throttle, brake, steer
        return throttle, brake, final_steering_angle
