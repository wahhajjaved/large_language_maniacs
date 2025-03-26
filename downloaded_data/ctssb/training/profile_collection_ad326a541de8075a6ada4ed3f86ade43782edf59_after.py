print(__file__)
from ophyd import (EpicsMotor, Device, Component as Cpt,
                   EpicsSignal, SubscriptionStatus)


class SampleStage(Device):
    rotary = Cpt(EpicsMotor, '-Ax:aY}Mtr')
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    z = Cpt(EpicsMotor, '-Ax:Z}Mtr')
    y = Cpt(EpicsMotor, '-Ax:Y}Mtr')

sample_stage1 = SampleStage('XF:07BMB-ES{Stg:1', name='sample_stage1')


class MonoTrajDesc(Device):
    filename = Cpt(EpicsSignal, '-Name')
    elem = Cpt(EpicsSignal, '-Elem')
    edge = Cpt(EpicsSignal, '-Edge')
    e0 = Cpt(EpicsSignal, '-E0')


class Monochromator(Device):
    _default_configuration_attrs = ('bragg', 'energy', 'pico', 'diag')
    _default_read_attrs = ('bragg', 'energy', 'pico', 'diag')
    "Monochromator"
    ip = '10.7.130.93'
    traj_filepath = '/home/xf07bm/trajectory/'
    bragg = Cpt(EpicsMotor, 'Mono:1-Ax:Scan}Mtr')
    energy = Cpt(EpicsMotor, 'Mono:1-Ax:E}Mtr')
    pico = Cpt(EpicsMotor, 'Mono:1-Ax:Pico}Mtr')
    diag = Cpt(EpicsMotor, 'Mono:1-Ax:Diag}Mtr')

    main_motor_res = Cpt(EpicsSignal, 'Mono:1-Ax:Scan}Mtr.MRES')

    # The following are related to trajectory motion
    lut_number = Cpt(EpicsSignal, 'MC:03}LUT-Set')
    lut_number_rbv = Cpt(EpicsSignal, 'MC:03}LUT-Read')
    lut_start_transfer = Cpt(EpicsSignal, 'MC:03}TransferLUT')
    lut_transfering = Cpt(EpicsSignal, 'MC:03}TransferLUT-Read')
    trajectory_loading = Cpt(EpicsSignal, 'MC:03}TrajLoading')
    traj_mode = Cpt(EpicsSignal, 'MC:03}TrajFlag1-Set')
    traj_mode_rbv = Cpt(EpicsSignal, 'MC:03}TrajFlag1-Read')
    enable_ty = Cpt(EpicsSignal, 'MC:03}TrajFlag2-Set')
    enable_ty_rbv = Cpt(EpicsSignal, 'MC:03}TrajFlag2-Read')
    cycle_limit = Cpt(EpicsSignal, 'MC:03}TrajRows-Set')
    cycle_limit_rbv = Cpt(EpicsSignal, 'MC:03}TrajRows-Read')
    enable_loop = Cpt(EpicsSignal, 'MC:03}TrajLoopFlag-Set')
    enable_loop_rbv = Cpt(EpicsSignal, 'MC:03}TrajLoopFlag')

    prepare_trajectory = Cpt(EpicsSignal, 'MC:03}PrepareTraj')
    trajectory_ready = Cpt(EpicsSignal, 'MC:03}TrajInitPlc-Read')
    start_trajectory = Cpt(EpicsSignal, 'MC:03}StartTraj')
    stop_trajectory = Cpt(EpicsSignal, 'MC:03}StopTraj')
    trajectory_running = Cpt(EpicsSignal,'MC:03}TrajRunning', write_pv='MC:03}TrajRunning-Set')
    trajectory_progress = Cpt(EpicsSignal,'MC:03}TrajProgress')
    trajectory_name = Cpt(EpicsSignal, 'MC:03}TrajFilename')

    traj1 = Cpt(MonoTrajDesc, 'MC:03}Traj:1')
    traj2 = Cpt(MonoTrajDesc, 'MC:03}Traj:2')
    traj3 = Cpt(MonoTrajDesc, 'MC:03}Traj:3')
    traj4 = Cpt(MonoTrajDesc, 'MC:03}Traj:4')
    traj5 = Cpt(MonoTrajDesc, 'MC:03}Traj:5')
    traj6 = Cpt(MonoTrajDesc, 'MC:03}Traj:6')
    traj7 = Cpt(MonoTrajDesc, 'MC:03}Traj:7')
    traj8 = Cpt(MonoTrajDesc, 'MC:03}Traj:8')
    traj9 = Cpt(MonoTrajDesc, 'MC:03}Traj:9')

    angle_offset = Cpt(EpicsSignal, 'Mono:1-Ax:E}Offset', limits=True)

    def __init__(self, *args, enc = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pulses_per_deg = 1/self.main_motor_res.value
        self.enc = enc

    def set(self, command):
        if command == 'prepare':

            # This function will receive Events from the IOC and check whether
            # we are seeing the trjectory become ready. It will return True
            # only if is sees (1) the old value is "not ready" and (2) the new
            # value is "ready".
            def callback(value, old_value, **kwargs):
                return (old_value == 0 and value == 1)

            # Creating this status object subscribes `callback` Events from the
            # IOC. Starting at this line, we are now listening for the IOC to
            # tell us is has become ready. When it does, this status object
            # will complete (status.done = True).
            status = SubscriptionStatus(self.trajectory_ready, callback)

            # Finally, now that we are litsening to the IOC, prepare the
            # trajectory.
            self.prepare_trajectory.set('1')  # Yes, the IOC requires a string.

            # Return the status object immediately, without waiting. The caller
            # will be able to watch for it to become done.
            return status

mono1 = Monochromator('XF:07BMA-OP{', enc = pb1.enc1, name='mono1')
mono1.energy.kind = 'hinted'
mono1.bragg.kind = 'hinted'
#mono1.pulses_per_deg = 23600*400/360
# set the angle offset to corret for the energy offset
mono1.angle_offset.set(-0.14881166238)


class Mirror(Device):
    hor_up = Cpt(EpicsMotor, '-Ax:XU}Mtr')
    hor_down = Cpt(EpicsMotor, '-Ax:XD}Mtr')
    vert_up = Cpt(EpicsMotor, '-Ax:YU}Mtr')
    vert_down_in = Cpt(EpicsMotor, '-Ax:YD1}Mtr')
    vert_down_out = Cpt(EpicsMotor, '-Ax:YD2}Mtr')
    bend = Cpt(EpicsMotor, '-Ax:BD}Mtr')

cm = Mirror('XF:07BMFE-OP{Mir:Col', name='cm')
fm = Mirror('XF:07BMA-OP{Mir:FM', name='fm')


class Slits(Device):
    top = Cpt(EpicsMotor, '-Ax:T}Mtr')
    bottom = Cpt(EpicsMotor, '-Ax:B}Mtr')
    outboard = Cpt(EpicsMotor, '-Ax:O}Mtr')
    inboard = Cpt(EpicsMotor, '-Ax:I}Mtr')

foe_slits = Slits('XF:07BMA-OP{Slt:1', name='foe_slits')
jj_slits = Slits('XF:07BMB-OP{Slt:1', name='jj_slits')


class FE_Slits(Device):
    top = Cpt(EpicsMotor, '1-Ax:T}Mtr')
    bottom = Cpt(EpicsMotor, '2-Ax:B}Mtr')
    outboard = Cpt(EpicsMotor, '1-Ax:O}Mtr')
    inboard = Cpt(EpicsMotor, '2-Ax:I}Mtr')

fe_slits = FE_Slits('FE:C07B-OP{Slt:', name = 'fe_slits')

ip_y_stage = EpicsMotor('XF:07BMB-OP{IBP:1-Ax:Y}Mtr', name='ip_y_stage')


class Table(Device):
    hor_up = Cpt(EpicsMotor, '-Ax:XU}Mtr')
    hor_down = Cpt(EpicsMotor, '-Ax:XD}Mtr')
    beam_dir = Cpt(EpicsMotor, '-Ax:Z}Mtr')
    vert_up = Cpt(EpicsMotor, '-Ax:YDU}Mtr')
    vert_down_in = Cpt(EpicsMotor, '-Ax:YDI}Mtr')
    vert_down_out = Cpt(EpicsMotor, '-Ax:YDO}Mtr')

exp_table = Table('XF:07BMB-OP{Asm:1', name='exp_table')
