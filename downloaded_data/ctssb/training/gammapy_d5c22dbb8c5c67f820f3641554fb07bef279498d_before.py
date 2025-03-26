# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, print_function, unicode_literals
import numpy as np
import copy
import astropy.units as u
import operator
from astropy.utils import lazyproperty
from ..utils.modeling import ParameterList
from ..utils.scripts import make_path
from ..maps import Map

__all__ = [
    'SourceLibrary',
    'SkyModel',
    'CompoundSkyModel',
    'SkyModelMapEvaluator',
]


class SourceLibrary(object):
    """Collection of `~gammapy.cube.models.SkyModel`

    Parameters
    ----------
    skymodels : list of `~gammapy.cube.models.SkyModel`
        Sky models

    Examples
    --------

    Read a SourceLibrary from an XML file::

        from gammapy.cube import SourceLibrary
        filename = '$GAMMAPY_EXTRA/test_datasets/models/fermi_model.xml'
        sourcelib = SourceLibrary.from_xml(filename)
    """

    def __init__(self, skymodels):
        self.skymodels = skymodels

    @classmethod
    def from_xml(cls, xml):
        """Read SourceLibrary from XML string"""
        from ..utils.serialization import xml_to_source_library
        return xml_to_source_library(xml)

    @classmethod
    def read(cls, filename):
        """Read SourceLibrary from XML file"""
        path = make_path(filename)
        xml = path.read_text()
        return self.from_xml(xml)

    def to_xml(self, filename):
        """Write SourceLibrary to XML file"""
        from ..utils.serialization import source_library_to_xml
        xml = source_library_to_xml(self)
        filename = make_path(filename)
        with filename.open('w') as output:
            output.write(xml)

    def to_compound_model(self):
        """Return `~gammapy.cube.models.CompoundSkyModel`"""
        compound_model = self.skymodels[0]
        for sky_model in self.skymodels[1:]:
            compound_model = compound_model + sky_model
        return compound_model


class SkyModel(object):
    """Sky model component.

    This model represents a factorised sky model.
    It has a `~gammapy.utils.modeling.ParameterList`
    combining the spatial and spectral parameters.

    TODO: add possibility to have a temporal model component also.

    Parameters
    ----------
    spatial_model : `~gammapy.image.models.SpatialModel`
        Spatial model (must be normalised to integrate to 1)
    spectral_model : `~gammapy.spectrum.models.SpectralModel`
        Spectral model
    name : str
        Model identifier
    """

    def __init__(self, spatial_model, spectral_model, name='SkyModel'):
        self._spatial_model = spatial_model
        self._spectral_model = spectral_model
        self.name = name
        self._init_parameters()

    def _init_parameters(self):
        """Create flat list of parameters"""
        parameters = self.spatial_model.parameters.copy()
        parameters.parameters += self.spectral_model.parameters.parameters
        self._parameters = parameters

    @property
    def spatial_model(self):
        """`~gammapy.image.models.SkySpatialModel`"""
        return self._spatial_model

    @property
    def spectral_model(self):
        """`~gammapy.spectrum.models.SpectralModel`"""
        return self._spectral_model

    @property
    def spatial_pars(self):
        """List of spatial parameter names"""
        return self.spatial_model.parameters.names

    @property
    def spectral_pars(self):
        """List of spectral parameter names"""
        return self.spectral_model.parameters.names

    @property
    def parameters(self):
        """Parameters (`~gammapy.utils.modeling.ParameterList`)"""
        return self._parameters

    @parameters.setter
    def parameters(self, parameters):
        self._parameters = parameters

    def __repr__(self):
        fmt = '{}(spatial_model={!r}, spectral_model={!r})'
        return fmt.format(self.__class__.__name__,
                          self.spatial_model, self.spectral_model)

    def __str__(self):
        ss = '{}\n\n'.format(self.__class__.__name__)
        ss += 'spatial_model = {}\n\n'.format(self.spatial_model)
        ss += 'spectral_model = {}\n'.format(self.spectral_model)
        return ss

    def evaluate(self, lon, lat, energy):
        """Evaluate the model at given points.

        Return differential surface brightness cube.
        At the moment in units: ``cm-2 s-1 TeV-1 deg-2``

        Parameters
        ----------
        lon, lat : `~astropy.units.Quantity`
            Spatial coordinates
        energy : `~astropy.units.Quantity`
            Energy coordinate

        Returns
        -------
        value : `~astropy.units.Quantity`
            Model value at the given point.
        """
        spatial_kwargs = dict()
        spectral_kwargs = dict()
        for par in self.parameters.parameters:
            if par.name in self.spatial_pars:
                spatial_kwargs[par.name] = par.quantity
            else:
                spectral_kwargs[par.name] = par.quantity

        val_spatial = self.spatial_model.evaluate(lon, lat, **spatial_kwargs)
        val_spectral = self.spectral_model.evaluate(energy, **spectral_kwargs)
        val_spectral = np.atleast_1d(val_spectral)[:, np.newaxis, np.newaxis]

        val = val_spatial * val_spectral

        return val.to('cm-2 s-1 TeV-1 deg-2')

    def copy(self):
        """A deep copy"""
        return copy.deepcopy(self)

    def __add__(self, skymodel):
        return CompoundSkyModel(self, skymodel, operator.add)

    def __radd__(self, model):
        return self.__add__(model)


class CompoundSkyModel(object):
    """Represents the algebraic combination of two
    `~gammapy.cube.models.SkyModel`

    Parameters
    ----------
    model1, model2 : `SkyModel`
        Two sky models
    operator : callable
        Binary operator to combine the models
    """

    def __init__(self, model1, model2, operator):
        self.model1 = model1
        self.model2 = model2
        self.operator = operator

    # TODO: Think about how to deal with covariance matrix
    @property
    def parameters(self):
        """Parameters (`~gammapy.utils.modeling.ParameterList`)"""
        val = self.model1.parameters.parameters + self.model2.parameters.parameters
        return ParameterList(val)

    @parameters.setter
    def parameters(self, parameters):
        idx = len(self.model1.parameters.parameters)
        self.model1.parameters.parameters = parameters.parameters[:idx]
        self.model2.parameters.parameters = parameters.parameters[idx:]

    def __str__(self):
        ss = self.__class__.__name__
        ss += '\n    Component 1 : {}'.format(self.model1)
        ss += '\n    Component 2 : {}'.format(self.model2)
        ss += '\n    Operator : {}'.format(self.operator)
        return ss

    def evaluate(self, lon, lat, energy):
        """Evaluate the compound model at given points.

        Return differential surface brightness cube.
        At the moment in units: ``cm-2 s-1 TeV-1 deg-2``

        Parameters
        ----------
        lon, lat : `~astropy.units.Quantity`
            Spatial coordinates
        energy : `~astropy.units.Quantity`
            Energy coordinate

        Returns
        -------
        value : `~astropy.units.Quantity`
            Model value at the given point.
        """
        val1 = self.model1.evaluate(lon, lat, energy)
        val2 = self.model2.evaluate(lon, lat, energy)

        return self.operator(val1, val2)


class SkyModelMapEvaluator(object):
    """Sky model evaluation on maps.

    This is a first attempt to compute flux as well as predicted counts maps.

    The basic idea is that this evaluator is created once at the start
    of the analysis, and pre-computes some things.
    It it then evaluated many times during likelihood fit when model parameters
    change, re-using pre-computed quantities each time.
    At the moment it does some things, e.g. cache and re-use energy and coordinate grids,
    but overall it is not an efficient implementation yet.

    For now, we only make it work for 3D WCS maps with an energy axis.
    No HPX, no other axes, those can be added later here or via new
    separate model evaluator classes.

    We should discuss how to organise the model and IRF evaluation code,
    and things like integrations and convolutions in a good way.

    Parameters
    ----------
    sky_model : `~gammapy.cube.models.SkyModel`
        Sky model
    exposure : `~gammapy.maps.Map`
        Exposure map
    psf : `~gammapy.cube.PSFKernel`
        PSF kernel
    background : `~gammapy.maps.Map`
        background map
    """

    def __init__(self, sky_model=None, exposure=None, psf=None, background=None):
        self.sky_model = sky_model
        self.exposure = exposure
        self.psf = psf
        self.background = background

    @lazyproperty
    def geom(self):
        return self.exposure.geom

    @lazyproperty
    def geom_image(self):
        return self.geom.to_image()

    @lazyproperty
    def energy_center(self):
        """Energy axis bin centers (`~astropy.units.Quantity`)"""
        energy_axis = self.geom.axes[0]
        energy = energy_axis.center * energy_axis.unit
        return energy

    @lazyproperty
    def energy_edges(self):
        """Energy axis bin edges (`~astropy.units.Quantity`)"""
        energy_axis = self.geom.axes[0]
        energy = energy_axis.edges * energy_axis.unit
        return energy

    @lazyproperty
    def energy_bin_width(self):
        """Energy axis bin widths (`astropy.units.Quantity`)"""
        return np.diff(self.energy_edges)

    @lazyproperty
    def lon_lat(self):
        """Spatial coordinate pixel centers.

        Returns ``lon, lat`` tuple of `~astropy.units.Quantity`.
        """
        lon, lat = self.geom_image.get_coord()
        return lon * u.deg, lat * u.deg

    @lazyproperty
    def lon(self):
        return self.lon_lat[0]

    @lazyproperty
    def lat(self):
        return self.lon_lat[1]

    @lazyproperty
    def solid_angle(self):
        """Solid angle per pixel"""
        return self.geom.solid_angle()

    @lazyproperty
    def bin_volume(self):
        """Map pixel bin volume (solid angle times energy bin width)."""
        omega = self.solid_angle
        de = self.energy_bin_width
        de = de[:, np.newaxis, np.newaxis]
        return omega * de

    def compute_dnde(self):
        """Compute model differential flux at map pixel centers.

        Returns
        -------
        model_map : `~gammapy.map.Map`
            Sky cube with data filled with evaluated model values.
            Units: ``cm-2 s-1 TeV-1 deg-2``
        """
        coord = (self.lon, self.lat, self.energy_center)
        dnde = self.sky_model.evaluate(*coord)
        return dnde

    def compute_flux(self):
        """Compute model integral flux over map pixel volumes.

        For now, we simply multiply dnde with bin volume.
        """
        dnde = self.compute_dnde()
        volume = self.bin_volume
        flux = dnde * volume
        return flux.to('cm-2 s-1')

    def apply_aeff(self, flux):
        """Compute npred cube

        For now just divide flux cube by exposure
        """
        npred_ = (flux * self.exposure.quantity).to('')
        npred = Map.from_geom(self.geom, unit='')
        npred.data = npred_.value
        return npred

    def apply_psf(self, npred):
        """Convolve npred cube with PSF"""
        return self.psf.apply(npred)

    def compute_npred(self):
        """Evaluate model predicted counts.
        """
        flux = self.compute_flux()
        npred = self.apply_aeff(flux)
        if self.psf is not None:
            npred = self.apply_psf(npred)
        if self.background:
            npred.data += self.background.data
        return npred.data
