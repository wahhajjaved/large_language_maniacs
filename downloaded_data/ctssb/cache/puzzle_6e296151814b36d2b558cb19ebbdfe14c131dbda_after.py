# apps.img.algorithms

# local
from apps.img.util import cut_to_black, create_bulk_from_image_set, nonzero_mean, edge_image
from apps.expt.util import generate_id_token

# util
import os
from scipy.misc import imsave
from scipy.ndimage.filters import gaussian_filter as gf
from scipy.ndimage.measurements import center_of_mass as com
from skimage import exposure
import numpy as np
from scipy.ndimage.measurements import label
import matplotlib.pyplot as plt

# methods
### STEP 2: Generate images for tracking
def mod_step02_tracking(composite, mod_id, algorithm):
  bf_set = composite.gons.filter(channel__name='1')
  gfp_set = composite.gons.filter(channel__name='0')

  # template
  template = composite.templates.get(name='source') # SOURCE TEMPLATE

  # channel
  tracking_channel, tracking_channel_created = composite.channels.get_or_create(name='-trackingimg')

  # iterate over frames
  for t in range(composite.series.ts):
    # 1. check if exists
    tracking_gon, tracking_gon_created = composite.gons.get_or_create(experiment=composite.experiment, series=composite.series, channel=tracking_channel, template=template, t=t)
    if tracking_gon_created:
      print('step02 | processing mod_step02_tracking t{}... created.               '.format(t), end='\r')
      tracking_gon.set_origin(0, 0, 0, t)
      tracking_gon.set_extent(composite.series.rs, composite.series.cs, 1)

      # 2. get components
      bf_gon = bf_set.get(t=t)
      bf_gon = bf_gon.gons.get(z=int(bf_gon.zs/2.0))
      bf = exposure.rescale_intensity(bf_gon.load() * 1.0)

      gfp_gon = gfp_set.get(t=t)
      gfp = exposure.rescale_intensity(gfp_gon.load() * 1.0)

      # 3. calculations
      gfp_smooth = gf(gfp, sigma=2)
      gfp_smooth = np.sum(gfp_smooth, axis=2) / 14.0 # completely arbitrary factor

      product = bf + gfp_smooth # superimposes the (slightly) smoothed gfp onto the bright field.

      # 4. save array
      tracking_gon.array = product

      tracking_gon.save_array(composite.experiment.tracking_path, template)
      tracking_gon.save()

    else:
      print('step02 | processing mod_step02_tracking t{}... already exists.'.format(t), end='\r')

mod_step02_tracking.description = ''

### STEP 3: combine channels for recognition
def mod_step03_pmod(composite, mod_id, algorithm):
  bf_set = composite.gons.filter(channel__name='1')
  gfp_set = composite.gons.filter(channel__name='0')

  # template
  template = composite.templates.get(name='source') # SOURCE TEMPLATE

  # channel
  channel, channel_created = composite.channels.get_or_create(name='-pmod')

  # iterate over frames
  for t in range(composite.series.ts):

    # 1. check if exists
    pmod_gon, pmod_gon_created = composite.gons.get_or_create(experiment=composite.experiment, series=composite.series, channel=channel, template=template, t=t)

    if pmod_gon_created:
      bf_gon = bf_set.get(t=t)
      print('step03 | processing mod_step03_pmod t{}... created.             '.format(t), end='\r')
      pmod_gon.set_origin(bf_gon.r, bf_gon.c, bf_gon.z, bf_gon.t)
      pmod_gon.set_extent(bf_gon.rs, bf_gon.cs, bf_gon.zs)

      # 2. get components
      bf = exposure.rescale_intensity(bf_gon.load() * 1.0)

      gfp_gon = gfp_set.get(t=t)
      gfp = exposure.rescale_intensity(gfp_gon.load() * 1.0)

      # 3. calculations
      gfp_smooth = exposure.rescale_intensity(gf(gfp, sigma=5)) / 2.0
      # gfp_reduced_glow = gfp_smooth * gfp_smooth

      # product = gfp_reduced_glow * bf
      product = bf * gfp_smooth

      # 4. save array
      pmod_gon.array = product

      pmod_gon.save_array(composite.experiment.composite_path, template)
      pmod_gon.save()

    else:
      print('step03 | processing mod_step03_pmod t{}... already exists.        '.format(t), end='\r')

mod_step03_pmod.description = 'Scale portions of the brightfield using the gfp density.'

def mod_step04_region_img(composite, mod_id, algorithm):
  bf_set = composite.gons.filter(channel__name='1')

  # template
  template = composite.templates.get(name='source') # SOURCE TEMPLATE

  # channel
  channel, channel_created = composite.channels.get_or_create(name='-regionimg')

  # iterate over frames
  for t in range(composite.series.ts):

    # 1. check if exists
    region_img_gon, region_img_gon_created = composite.gons.get_or_create(experiment=composite.experiment, series=composite.series, channel=channel, template=template, t=t)
    if region_img_gon_created:
      print('step03 | processing mod_step04_region_img t{}... created.              '.format(t), end='\r')
      region_img_gon.set_origin(bf_gon.r, bf_gon.c, 0, bf_gon.t)
      region_img_gon.set_extent(bf_gon.rs, bf_gon.cs, bf_gon.zs)

      # 2. get components
      bf_great_gon = bf_set.get(t=t)
      bf_gon = bf_great_gon.gons.get(z=int(bf_great_gon.zs / 2.0))
      bf = exposure.rescale_intensity(bf_gon.load() * 1.0)

      # 3. calculations
      # None

      # 4. save array
      region_img_gon.array = bf

      region_img_gon.save_array(composite.experiment.region_img_path, template)
      region_img_gon.save()

    else:
      print('step03 | processing mod_step04_region_img t{}... already exists.'.format(t), end='\r')

mod_step04_region_img.description = 'Raw brightfield image at the centre of the environment'

def mod_step08_reduced(composite, mod_id, algorithm):
  # paths
  template = composite.templates.get(name='source') # SOURCE TEMPLATE

  # channels
  pmod_reduced_channel, pmod_reduced_channel_created = composite.channels.get_or_create(name='-pmodreduced')
  bf_reduced_channel, bf_reduced_channel_created = composite.channels.get_or_create(name='-bfreduced')

  # image sets
  pmod_set = composite.gons.filter(channel__name='-pmod')
  bf_set = composite.gons.filter(channel__name='1')

  # create batches
  batch = 0
  max_batch_size = 100

  # iterate over frames
  for t in range(composite.series.ts):
    print('step08 | processing mod_step08_reduced t{}...'.format(t), end='\n' if t==composite.series.ts-1 else '\r')

    # 1. get
    pmod_gon = pmod_set.get(t=t)
    bf_gon = bf_set.get(t=t)

    # 2. for each unique z value of the markers, make a gon and add it to the pmod_reduced channel
    marker_z_values = list(np.unique([marker.z for marker in composite.series.markers.filter(t=t)]))

    for z in marker_z_values:
      # save z range
      lower_z = z - 1 if z - 1 >= 0 else 0
      upper_z = z + 2 if z + 2 < composite.series.zs else composite.series.zs

      for sz in range(lower_z,upper_z):

        # check batch and make folders, set url
        if not os.path.exists(os.path.join(composite.experiment.cp_path, composite.series.name, str(batch))):
          os.makedirs(os.path.join(composite.experiment.cp_path, composite.series.name, str(batch)))

        if len(os.listdir(os.path.join(composite.experiment.cp_path, composite.series.name, str(batch))))==max_batch_size:
          batch += 1
          if not os.path.exists(os.path.join(composite.experiment.cp_path, composite.series.name, str(batch))):
            os.makedirs(os.path.join(composite.experiment.cp_path, composite.series.name, str(batch)))

        root = os.path.join(composite.experiment.cp_path, composite.series.name, str(batch)) # CP PATH

        # pmod
        if pmod_reduced_channel.paths.filter(t=t, z=sz).count()==0:
          rpmod_gon = composite.gons.create(experiment=composite.experiment, series=composite.series, channel=pmod_reduced_channel, template=template)
          rpmod_gon.set_origin(0, 0, sz, t)
          rpmod_gon.set_extent(composite.series.rs, composite.series.cs, 1)

          rpmod_gon.array = pmod_gon.gons.get(z=sz).load()

          rpmod_gon.save_array(root, template)
          rpmod_gon.save()

        # bf
        if bf_reduced_channel.paths.filter(t=t, z=sz).count()==0:
          rbf_gon = composite.gons.create(experiment=composite.experiment, series=composite.series, channel=bf_reduced_channel, template=template)
          rbf_gon.set_origin(0, 0, sz, t)
          rbf_gon.set_extent(composite.series.rs, composite.series.cs, 1)

          rbf_gon.array = bf_gon.gons.get(z=sz).load()

          rbf_gon.save_array(root, template)
          rbf_gon.save()

mod_step08_reduced.description = 'Include bf channel to aid recognition'

def mod_step09_regions(composite, mod_id, algorithm):
  # paths
  template = composite.templates.get(name='region') # REGION TEMPLATE
  mask_template = composite.templates.get(name='mask')

  # get region img set that has the region template
  region_img_set = composite.gons.filter(channel__name='-regionimg', template__name='region')

  # channel
  region_channel, region_channel_created = composite.channels.get_or_create(name='-regions')

  # iterate
  for t in range(composite.series.ts):
    region_img = region_img_set.filter(t=t)
    if region_img.count()==0:
      region_img = region_img_set.get(t=t-1)
    else:
      region_img = region_img_set.get(t=t)

    # for each image, determine unique values of labelled array
    # make gon with label array and save

    region_gon = composite.gons.create(experiment=composite.experiment, series=composite.series, channel=region_channel, template=template)
    region_gon.set_origin(0, 0, 0, t)
    region_gon.set_extent(composite.series.rs, composite.series.cs, 1)

    # modify image
    region_array = region_img.load()
    region_array = region_array[:,:,0]
    region_array[region_array>0] = 1
    region_array, n = label(region_array)

    region_gon.array = region_array.copy()
    region_gon.save_array(os.path.join(composite.experiment.mask_path, composite.series.name), template)

    for unique_value in [u for u in np.unique(region_array) if u>0]:
      # 1. cut image to single value
      unique_image = np.zeros(region_array.shape)
      unique_image[region_array==unique_value] = 1
      cut, (r,c,rs,cs) = cut_to_black(unique_image)

      # 2. make gon with cut image and associate to gon
      gon = region_gon.gons.create(experiment=composite.experiment, series=composite.series, channel=region_channel, template=mask_template)
      gon.id_token = generate_id_token('img','Gon')
      gon.set_origin(r,c,0,t)
      gon.set_extent(rs,cs,1)

      gon.array = cut.copy()

      gon.save_mask(composite.experiment.sub_mask_path)
      gon.save()

      # 3. make mask with cut image and associate to gon2
      mask = region_gon.masks.create(composite=composite, channel=region_channel, mask_id=unique_value)
      mask.set_origin(r,c,0)
      mask.set_extent(rs,cs)

mod_step09_regions.description = 'Convert gimp images into binary masks'

def mod_step11_masks(composite, mod_id, algorithm):
  # templates
  cp_template = composite.templates.get(name='cp')
  mask_template = composite.templates.get(name='mask')

  for t in range(composite.series.ts):

    # get gfp
    gfp_gon = composite.gons.get(channel__name='0', t=t)
    smooth_gfp = gf(exposure.rescale_intensity(gfp_gon.load() * 1.0), sigma=3)

    # mask img set
    mask_gon_set = composite.gons.filter(channel__name__in=['bfreduced','pmodreduced'], template__name='cp', t=t)

    for mask_gon in mask_gon_set:
      # load and get unique values
      mask_array = mask_gon.load()

      # unique
      for unique_value in [u for u in np.unique(mask_array) if u>0]:
        print('step11 | processing mod_step11_masks... {}: {} masks   '.format(mask_gon.paths.get().file_name, unique_value), end='\r')

        # 1. cut image to single value
        unique_image = mask_array==unique_value
        cut, (r,c,rs,cs) = cut_to_black(unique_image)

        # smaller masked gfp array
        mini_masked_array = np.ma.array(smooth_gfp[r:r+rs, c:c+cs, :], mask=np.dstack([np.invert(cut)]*smooth_gfp.shape[2]), fill_value=0)

        # squeeze into column
        column = np.sum(np.sum(mini_masked_array.filled(), axis=0), axis=0)

        # details
        max_z = np.argmax(column)
        mean = np.mean(column)
        std = np.std(column)

        # 3. make mask with cut image and associate to gon2
        mask = mask_gon.masks.create(composite=composite, channel=mask_gon.channel, mask_id=unique_value)
        mask.set_origin(r,c,mask_gon.z)
        mask.set_extent(rs,cs)
        mask.set_gfp(max_z, mean, std)

def mod_step13_cell_masks(composite, mod_id, algorithm):
  # paths
  template = composite.templates.get(name='mask') # MASK TEMPLATE

  # create batches
  batch = 0
  max_batch_size = 100

  # channel
  cell_mask_channel, cell_mask_channel_created = composite.channels.get_or_create(name='cellmask')

  # iterate over frames
  for t in range(composite.series.ts):
    print('step13 | processing mod_step13_cell_masks t{}...                                         '.format(t), end='\r')

    # one mask for each marker
    markers = composite.series.markers.filter(t=t)

    # 1. get masks
    mask_gon_set = composite.gons.filter(channel__name__in=['pmodreduced','bfreduced'], t=t)
    bulk = create_bulk_from_image_set(mask_gon_set)
    mask_mean_max = np.max([mask.mean for mask in composite.masks.all()])

    for m,marker in enumerate(markers):
      print('step13 | processing mod_step13_cell_masks t{}, marker {}/{}...                                         '.format(t, m, len(markers)), end='\r')
      # marker parameters
      r, c, z = marker.r, marker.c, marker.z
      other_marker_posiitions = [(m.r,m.c) for m in markers.exclude(pk=marker.pk)]

      # get primary mask
      primary_mask = np.zeros(composite.series.shape(), dtype=float) # blank image

      mask_uids = [(i, uid) for i,uid in enumerate(bulk.gon_stack[r,c,:]) if uid>0]
      for i,uid in mask_uids:
        gon_pk = bulk.rv[i]
        mask = composite.masks.get(gon__pk=gon_pk, mask_id=uid)
        mask_array = (bulk.slice(pk=mask.gon.pk)==mask.mask_id).astype(float)

        # modify mask array based on parameters
        mask_z, mask_max_z, mask_mean, mask_std = mask.z, mask.max_z, mask.mean, mask.std

        z_term = 1.0 / (1.0 + 0.1*np.abs(z - mask_z)) # suppress z levels at increasing distances from marker
        max_z_term = 1.0 / (1.0 + 0.1*np.abs(z - mask_max_z)) # suppress z levels at increasing distances from marker
        mean_term = mask_mean / mask_mean_max # raise mask according to mean
        std_term = 1.0

        mask_array = mask_array * z_term * max_z_term * mean_term * std_term

        # add to primary mask
        primary_mask += mask_array

      # get secondary mask - get unique masks that touch the edge of the primary mask
      secondary_mask = np.zeros(composite.series.shape(), dtype=float) # blank image

      secondary_mask_uids = []
      edges = np.where(edge_image(primary_mask>0))
      for r, c in zip(*edges):
        for i,uid in enumerate(bulk.gon_stack[r,c,:]):
          if (i,uid) not in secondary_mask_uids and (i,uid) not in mask_uids and uid>0:
            secondary_mask_uids.append((i,uid))

      for i,uid in secondary_mask_uids:
        print('step13 | processing mod_step13_cell_masks t{}, marker {}/{}, secondary {}/{}...                                         '.format(t, m, len(markers), i, len(secondary_mask_uids)), end='\r')
        gon_pk = bulk.rv[i]
        mask = composite.masks.get(gon__pk=gon_pk, mask_id=uid)
        mask_array = (bulk.slice(pk=mask.gon.pk)==mask.mask_id).astype(float)

        # modify mask array based on parameters
        mask_z, mask_max_z, mask_mean, mask_std = mask.z, mask.max_z, mask.mean, mask.std

        z_term = 1.0 / (1.0 + 0.1*np.abs(z - mask_z)) # suppress z levels at increasing distances from marker
        max_z_term = 1.0 / (1.0 + 0.1*np.abs(z - mask_max_z)) # suppress z levels at increasing distances from marker
        mean_term = mask_mean / mask_mean_max # raise mask according to mean
        std_term = 1.0

        foreign_marker_condition = 1.0 # if the mask contains a different marker
        foreign_marker_match = False
        foreign_marker_counter = 0
        while not foreign_marker_match and foreign_marker_counter!=len(other_marker_posiitions)-1:
          r, c = other_marker_posiitions[foreign_marker_counter]
          foreign_marker_match = (mask_array>0)[r,c]
          if foreign_marker_match:
            foreign_marker_condition = 0.0
          foreign_marker_counter += 1

        mask_array = mask_array * z_term * max_z_term * mean_term * std_term * foreign_marker_condition

        # add to primary mask
        secondary_mask += mask_array

      print('step13 | processing mod_step13_cell_masks t{}, marker {}/{}, saving square mask...                                         '.format(t, m, len(markers)), end='\n' if t==composite.series.ts-1 else '\r')
      cell_mask = primary_mask + secondary_mask

      # finally, mean threshold mask
      cell_mask[cell_mask<nonzero_mean(cell_mask)] = 0
      cell_mask[cell_mask<nonzero_mean(cell_mask)] = 0

      # cut to size
      # I want every mask to be exactly the same size -> 128 pixels wide
      # I want the centre of the mask to be in the centre of image
      # Add black space around even past the borders of larger image
      # 1. determine centre of mass
      com_r, com_c = com(cell_mask)

      # 2. cut to black and preserve boundaries
      cut, (cr, cc, crs, ccs) = cut_to_black(cell_mask)

      # 3. create new square image
      mask_square = np.zeros((256,256), dtype=float)

      # 4. place cut inside square image using the centre of mass and the cut boundaries to hit the centre
      dr, dc = int(128 + cr - com_r), int(128 + cc - com_c)

      # 5. preserve coordinates of square to position gon
      print('newline')
      print(cr, com_r, cc, com_c, dr, dr+crs, dc, dc+ccs)
      mask_square[dr:dr+crs,dc:dc+ccs] = cut

      # check batch and make folders, set url
      if not os.path.exists(os.path.join(composite.experiment.cp2_path, composite.series.name, str(batch))):
        os.makedirs(os.path.join(composite.experiment.cp2_path, composite.series.name, str(batch)))

      if len(os.listdir(os.path.join(composite.experiment.cp2_path, composite.series.name, str(batch))))==max_batch_size:
        batch += 1
        if not os.path.exists(os.path.join(composite.experiment.cp2_path, composite.series.name, str(batch))):
          os.makedirs(os.path.join(composite.experiment.cp2_path, composite.series.name, str(batch)))

      root = os.path.join(composite.experiment.cp2_path, composite.series.name, str(batch)) # CP PATH

      # cell mask gon
      cell_mask_gon = composite.gons.create(experiment=composite.experiment, series=composite.series, channel=cell_mask_channel, template=template)
      cell_mask_gon.set_origin(cr-dr, cc-dc, z, t)
      cell_mask_gon.set_extent(crs, ccs, 1)

      id_token = generate_id_token('img','Gon')
      cell_mask_gon.id_token = id_token

      file_name = template.rv.format(id_token)
      url = os.path.join(root, file_name)

      imsave(url, mask_square.copy())
      cell_mask_gon.paths.create(composite=composite, channel=cell_mask_channel, template=template, url=url, file_name=file_name, t=t, z=z)

      # associate with marker
      marker.gon = cell_mask_gon
      cell_mask_gon.marker = marker
      marker.save()

      cell_mask_gon.save()
