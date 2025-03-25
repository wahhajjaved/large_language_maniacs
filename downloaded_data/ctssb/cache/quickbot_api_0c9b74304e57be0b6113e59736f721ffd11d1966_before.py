"""
PID controller
"""


class PID:
    """
    Classical PID controller.

    Example:

        pid = PID(Kp=1.0, Ki=0.1, Kd=0.05)

        for input in read_input():
            output = pid(input)
    """

    def __init__(self, Kp, Ki=0, Kd=0, x0=0, integral_limit=10.0):
        """
        Creates an instance of PID controller.

            Kp - proportional gain
            Ki - integral gain
            Kd - derivative gain
            x0 - initial input value (used to compute derivative term)
            gain_limit - prevents integral term from getting too large (typically because
                    of actuators saturation). If gain_limit is set to 1., then the integral and
                    derivative terms together can never exceed the proportional term.
                    Reasonable value is 2.0, that will allow integral (plus derivative) term
                    to contribute as much as twice the proportional term. Value of zero
                    effectively turns off integral and derivative terms. Large value does not
                    impose any limits, resulting in an ordinary PID behavior.
        """
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd

        self._x_prev = x0
        self._acc = 0
        self._integral_limit = integral_limit

    def __call__(self, x):
        self._acc += x

        # anti-saturation logic: do not allow integral contribution
        # to exceed gain limit
        if self._acc > self._integral_limit:
            self._acc = self._integral_limit
        elif self._acc < -self._integral_limit:
            self._acc = -self._integral_limit

        # integral and derivative PID terms
        out = self.Lp * x + self.Ki * self._acc + self.Kd * (x - self._x_prev)
        self._x_prev = x

        return out
