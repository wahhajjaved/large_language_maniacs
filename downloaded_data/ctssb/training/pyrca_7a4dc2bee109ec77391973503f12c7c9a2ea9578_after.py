from pyrca.properties.unit import Unit
from pyrca.properties.section import Section
from pyrca.properties.steel_compression import SteelCompression
from pyrca.properties.steel_tension import SteelTension
from pyrca.properties.node import Node
from pyrca.properties.beam_section import BeamSection
from pyrca.utils.conversion import *
from pyrca.utils.calculators import *
from pyrca.utils.beam_constants import *
from pyrca.analysis.beam_analysis_result import BeamAnalysisResult
from pyrca.analysis.stress_distribution import StressDistribution


def calculate_fs(fs: float, fy: float):
    """
    Determine what to use for fs.
    :param fs: Steel stress
    :param fy: Steel yield stress.
    :return:
    """
    return min(fs, fy)


def get_beta(fc_prime: float):
    """
    Whitney stress block beta calculator.
    :param fc_prime: Concrete compressive strength.
    :return:
    """
    _beta = 0.85

    if fc_prime > COMPRESSIVE_STRENGTH_THRESHOLD:
        _beta = 0.85 - 0.05 / 7 * (fc_prime - COMPRESSIVE_STRENGTH_THRESHOLD)

    # Limit beta to 0.65
    if _beta < 0.65:
        _beta = 0.65

    return _beta


class BeamAnalyses:
    beam_section: BeamSection = None            # Section to be analyzed
    moment: float = None                        # Moment load in N-mm
    minimum_steel_tension_area: float = None    # Minimum reinforcement for the cracking stage
    cracking_moment: float = None               # Mcr in N-mm
    curvature_after_crack: float = None         # Beam curvature right after cracking
    balanced_steel_tension: float = None        # Required steel area for balanced design
    unit: Unit = Unit.METRIC                    # Set the default unit
    section: Section = None

    def get_minimum_steel_tension_area(self):
        if self.unit == Unit.ENGLISH:
            return to_square_inches(self.minimum_steel_tension_area)
        return self.minimum_steel_tension_area

    def get_cracking_moment(self):
        if self.unit == Unit.ENGLISH:
            return to_english_moment(self.cracking_moment)
        return self.cracking_moment

    def get_balanced_steel_tension(self):
        if self.unit == Unit.ENGLISH:
            return to_square_inches(self.balanced_steel_tension)
        return self.balanced_steel_tension

    def uncracked_analysis(self) -> BeamAnalysisResult:
        """
        Analysis before cracking of concrete.
        :return: BeamAnalysisResult object
        """
        _analysis = BeamAnalysisResult()
        _section_geometry = self.beam_section.get_section()

        _fr = self.beam_section.get_fr()
        _Ec = self.beam_section.get_Ec()
        _h = _section_geometry.get_height()
        _Ac = _section_geometry.gross_area_of_concrete()
        _yc = _section_geometry.get_centroid()
        _d = self.beam_section.get_effective_depth()
        _d_prime = self.beam_section.steel_compression.get_d_prime(self.unit)
        _fy = self.beam_section.get_fy()

        _steel_tension = self.beam_section.steel_tension
        _steel_compression = self.beam_section.steel_compression

        _As = _steel_tension.get_total_area(self.unit)
        _As_prime = _steel_compression.get_total_area(self.unit)
        _strain_index = self.beam_section.concrete_strain_index

        _At = 0                                     # Total transformed area
        _n = self.beam_section.get_modular_ratio()  # Modular ratio

        # Calculate total area including transformed steel
        _At += _Ac
        _At += (_n - 1) * _As
        _At += (_n - 1) * _As_prime

        # Calculate moment of areas
        _ma = 0.0
        _ma += (_n - 1) * _As * _d
        _ma += (_n - 1) * _As_prime * _d_prime
        _ma += _Ac * _yc

        _kd = _ma / _At                                     # Neutral axis to extreme compression fiber
        _kd_elev = _section_geometry.get_neutral_axis_elevation()
        _highest_elev = get_highest_node(_section_geometry.main_section).y
        _ec = (_fr / _Ec) / (_h - _kd) * _kd                # Strain in concrete compression
        _fc = _ec * _Ec                                     # Concrete stress
        _fs = (_fr * ES * (_d - _kd)) / (_Ec * (_h - _kd))  # Stress in tension steel
        _fs_prime = (_fr * ES * (_kd - _d_prime)) / (_Ec * (_h - _kd))  # Stress in compression steel
        _compression_area = _section_geometry.get_area_above_axis(_kd_elev)
        _tension_area = _section_geometry.gross_area_of_concrete() - _compression_area

        # Compression concrete resultant
        _cc = self.compression_solid_volume_triangular(_kd, _highest_elev, _fc)

        # Solve for location of _cc from top
        _dy = _kd / COMPRESSION_SOLID_DY_ITERATION
        _myc = 0
        for _i in range(COMPRESSION_SOLID_DY_ITERATION, 0, -1):
            _compression_strip = self.beam_compression_strip_triangular(_i, _dy, _kd, _fc, _highest_elev)
            _ccy = _compression_strip[0] * _compression_strip[1] * _dy
            _myc += _ccy * (_kd - _i * _dy)
        _ycc = _myc / _cc

        # Tension concrete resultant
        _tc = self.tension_solid_volume_triangular(_h - _kd, _kd, _highest_elev, _fr)

        # Solve for location of _tc
        _myt = 0
        for i in range(COMPRESSION_SOLID_DY_ITERATION, 0, -1):
            _tension_strip = self.beam_tension_strip_triangular(i, _dy, _kd, _h - _kd, _fr, _highest_elev)
            _tcy = _tension_strip[0] * _tension_strip[1] * _dy
            _myt += _tcy * (_h - _kd - i * _dy)
        _yct = _myt / _tc

        _cs = _As_prime * _fs_prime     # Compression force in steel
        _ts = _As * _fs                 # Tension force on steel

        # Location of resultant of _cc and _cs
        _y_compression = (_cc * _ycc + _cs * _d_prime) / (_cc + _cs)

        # Cracking moment
        _mcr = _ts * (_d - _y_compression) + _tc * (_h - _y_compression - _yct)

        # Minimum steel using whitney stress block
        _mcr_trial = 0
        _a = 0.001
        _ytop = 0
        while _mcr_trial < _mcr:
            _ya = _highest_elev - _a
            _compression_area = _section_geometry.area_above_axis(_ya)
            _ytop = _section_geometry.centroid_above_axis(_ya)
            _mcr_trial = 0.85 * self.beam_section.get_fc_prime() * _compression_area * (_d - _ytop)
            _a += 0.001

        self.cracking_moment = _mcr
        self.minimum_steel_tension_area = _mcr / (_fy * (_d - _ytop))
        _curvature = _ec / _kd

        # Set the values for the BeamAnalysisResult
        _analysis.moment_c = _mcr
        _analysis.curvature_c = _curvature
        _analysis.kd = _kd

        return _analysis

    def beam_capacity_analysis(self, sd: StressDistribution) -> BeamAnalysisResult:
        """
        The main purpose of this method is to calculate the beam nominal moment capacity
        using the specified stress distribution.
        :param sd: Either the parabolic which was derived by integration and the
                    Whitney's rectangular stress block which is a close representation of
                    the parabolic.
        :return:
        """
        _analysis = BeamAnalysisResult()

        _section = self.beam_section.get_section()

        _ecu = MAX_CONCRETE_STRAIN
        _Es = ES
        _d = self.beam_section.get_effective_depth()
        _d_prime = self.beam_section.steel_compression.get_d_prime(self.unit)
        _fs = 0.0
        _fy = self.beam_section.get_fy()
        _As = self.beam_section.steel_tension.get_total_area(self.unit)
        _As_Prime = self.beam_section.steel_compression.get_total_area(self.unit)
        _fs_prime = _fy
        _cc = 0
        _cs = 0
        _fc_prime = self.beam_section.get_fc_prime()
        _fc = 0.85 * _fc_prime              # Limit for fc to use
        _kd_y = 0
        _compression_area = 0

        _As_calc = 0                        # As calculated
        _kd = 0.01
        _highest_elev = get_highest_node(self.beam_section.get_section().main_section).y

        if sd == StressDistribution.PARABOLIC:
            # For parabolic stress distribution

            # Find kd
            _iterator = COMPRESSION_SOLID_DY_ITERATION      # Number of iterations on fining kd.

            # Convert the iterator based on unit
            if self.unit == Unit.ENGLISH:
                _kd_iterator = 1 / MILLIMETER_PER_INCH
            else:
                _kd_iterator = 1

            while abs((_As_calc - _As) > 0.01 * _As):
                # Loop until the As provided is reached.
                _cs = 0
                _cc = self.compression_solid_volume_parabolic(_fc_prime, _kd, _ecu, _highest_elev)
                _fs = _ecu * _Es * (_d - _kd) / _kd
                _fs = calculate_fs(_fs, _fy)

                _fsPrime = _fs * (_kd - _d_prime) / (_d - _kd)
                _fsPrime = calculate_fs(_fs_prime, _fy)

                _cs += _As_Prime * _fs_prime

                _As_calc = (_cc + _cs) / _fs

                if _As_calc > _As:
                    while _As_calc > _As:
                        _kd -= _kd_iterator
                        _cc = self.compression_solid_volume_parabolic(_fc_prime, _kd, _ecu, _highest_elev)

                        _fs = _ecu * _Es * (_d - _kd) / _kd
                        _fs = calculate_fs(_fs, _fy)

                        _fsPrime = _fs * (_kd - _d_prime) / (_d - _kd)
                        _fsPrime = calculate_fs(_fs_prime, _fy)

                        _cs += _As_Prime * _fs_prime

                        _As_calc = (_cc + _cs) / _fs

                        _kd_iterator *= 0.5
                else:
                    _kd_iterator *= 1.5

                _kd += _kd_iterator

            _my = 0                 # Moment of compression solid to the top
            _y_bar = 0              # Centroid of compression solid from top
            _dy = _kd / _iterator

            for _i in range(_iterator, 0, -1):
                _compression_strip_component = self.beam_compression_strip_parabolic(
                    _i, _dy, _ecu, _kd, _fc_prime, _highest_elev
                )
                _fcy, _by = _compression_strip_component

                _ccy = _fcy * _by * _dy

                _my += _ccy * (_kd - _i * _dy)

            _y_bar = _my / _cc

            _moment = _cc * (_d - _y_bar) + _cs * (_d - _d_prime)
        else:
            # For Whitney stress block
            _beta = get_beta(_fc_prime)

            _a = 0.001                  # Compression block height
            _As_calc = 0
            _kdy = 0
            while _As_calc < _As:
                _kd = _a / _beta
                _fs = _ecu * _Es * (_d - _kd) / _kd
                _fs = calculate_fs(_fs, _fy)

                _kdy = _highest_elev - _a
                _compression_area = _section.area_above_axis(_kdy)
                _cc = _fc * _compression_area

                _fsPrime = _fs * (_kd - _d_prime) / (_d - _kd)
                _fsPrime = calculate_fs(_fs_prime, _fy)

                _cs = _As_Prime * _fs_prime

                _As_calc = (_cc + _cs) / _fs
                _a += 0.001

            _compression_centroid = _section.centroid_above_axis(_kdy)
            _moment = _cc * (_d - _compression_centroid) + _cs * (_d - _d_prime)

        # Set values for analysis
        _analysis.moment_c = _moment
        _analysis.kd = _kd
        _analysis.curvature_c = _ecu / _kd

        return _analysis

    def beam_balanced_analysis(self, sd: StressDistribution) -> BeamAnalysisResult:
        """
        Analyze the beam using the palance condition.
        :param sd:
        :return:
        """
        _section = self.beam_section.get_section()

        _ecu = MAX_CONCRETE_STRAIN
        _d = self.beam_section.get_effective_depth()
        _d_prime = self.beam_section.steel_compression.get_d_prime(self.unit)
        _As_prime = self.beam_section.steel_compression.get_total_area(self.unit)
        _fy = self.beam_section.get_fy()
        _fc_prime = self.beam_section.get_fc_prime()
        _fc = 0.85 * _fc_prime
        _highest_elev = get_highest_node(_section.main_section).y
        _kd = _ecu * ES * _d / (_fy + _ecu * ES)

        if sd == StressDistribution.PARABOLIC:
            _cc = self.compression_solid_volume_parabolic(_fc_prime, _kd, _ecu, _highest_elev)

        else:
            _beta = get_beta(_fc_prime)
            _a = _beta * _kd
            _kdy = _highest_elev - _a
            _compression_area = _section.area_above_axis(_kdy)
            _cc = _fc * _compression_area
        _fs_prime = _ecu * ES * (_kd - _d_prime) / _kd
        _fs_prime = calculate_fs(_fs_prime, _fy)
        _cs = _As_prime * _fs_prime

        _As_b = (_cc + _cs) / _fy

        # Get the location of the resultant concrete compression
        _iterator = COMPRESSION_SOLID_DY_ITERATION
        _dy = _kd / _iterator
        _my = 0
        for _i in range(_iterator, 0, -1):
            _compression_strip_component = self.beam_compression_strip_parabolic(
                _i, _dy, _ecu, _kd, _fc_prime, _highest_elev
            )
            _fc1, _b1 = _compression_strip_component
            _cc = _fc1 * _b1 * _dy
            _my += _cc * (_kd - _i * _dy)
        _y_bar = _my / _cc          # Location of compression concrete resultant from top

        _moment_balance = _cc * (_d - _y_bar) + _cs * (_d - _d_prime)

        self.balanced_steel_tension = _As_b

        _result = BeamAnalysisResult()
        _result.curvature_c = _ecu / _kd
        _result.kd = _kd
        _result.moment_c = _moment_balance

        return _result

    def compression_solid_volume_parabolic(self, fc_prime, kd, ecu, highest_elev):
        """
        Concrete compression solid magnitude using parabolic stress block.
        :param fc_prime:
        :param kd:
        :param ecu:
        :param highest_elev:
        :return:
        """
        _cc = 0
        _iterator = COMPRESSION_SOLID_DY_ITERATION
        _dy = kd / _iterator
        for i in range(_iterator, 0, -1):
            _compression_strip_component = self.beam_compression_strip_parabolic(
                i, _dy, ecu, kd, fc_prime, highest_elev
            )
            _fcy, _by = _compression_strip_component
            _cc += _fcy * _by * _dy

        return _cc

    def compression_solid_volume_triangular(self, kd, highest_elev, fc):
        """
        Calculates the volume of compression solid for uncrack beam section
        :param kd:
        :param highest_elev:
        :param fc:
        :return:
        """
        _cc = 0

        _iterator = COMPRESSION_SOLID_DY_ITERATION
        _dy = kd / _iterator
        for i in range(_iterator, 0, -1):
            _compression_strip_component = self.beam_compression_strip_triangular(
                i, _dy, kd, fc, highest_elev
            )
            _fcy, _by = _compression_strip_component
            _cc += _fcy * _by * _dy;

        return _cc

    def tension_solid_volume_triangular(self, z, kd, highest_elev, fr):
        """
        Calculates the volume of tension solid for uncracked beam section
        :param z:
        :param kd:
        :param highest_elev:
        :param fr:
        :return:
        """
        _tc = 0
        _iterator = 10000000
        _dy = z / _iterator
        for i in range(_iterator, 0, -1):
            _tension_strip_component = self.beam_tension_strip_triangular(
                i, _dy, kd, z, fr, highest_elev
            )
            _fry, _by = _tension_strip_component
            _tc += _fry * _by * _dy

        return _tc

    def beam_compression_strip_parabolic(self, i, dy, ecu, kd, fc_prime, highest_elev):
        """
        Beam compression solid strip
        :param i: ith strip for integration
        :param dy: height of strip
        :param ecu: maximum concrete strain
        :param kd: trial or value of height of compression block
        :param fc_prime: concrete compressive strength
        :param highest_elev: top elevation of beam section
        :return: b(y) and fc(y)
        """
        _eco = 2 * 0.85 * fc_prime / (4700 * math.sqrt(fc_prime))
        _y = i * dy
        _ecy = ecu * _y / kd        # Strain at y
        if _ecy < _eco:
            _fc = 0.85 * fc_prime * (2 * _ecy / _eco - math.pow((_ecy / _eco), 2))
        else:
            _fc = 0.85 * fc_prime
        _y_elev = highest_elev - kd + _y
        _b = self.beam_section.get_section().get_effective_width(_y_elev)
        return _fc, _b

    def beam_compression_strip_triangular(self, i, dy, kd, fc, highest_elev):
        """
        Beam compression solid strip
        :param i: ith strip for integration
        :param dy: height of strip
        :param kd: trial or actual value of height of compression block
        :param fc:
        :param highest_elev: Top elevation of beam section.
        :return: b(y) and fc(y)
        """
        _y = i * dy
        _fcy = fc * _y / kd
        _y_elev = highest_elev - kd + _y
        _by = self.beam_section.get_section().get_effective_width(_y_elev)

        return _fcy, _by

    def beam_tension_strip_triangular(self, i, dy, kd, z, fr, highest_elev):
        _y = i * dy
        _fry = fr * _y / z
        _y_elev = highest_elev - kd - _y
        _by = self.beam_section.get_section().get_effective_width(_y_elev)

        return _fry, _by
