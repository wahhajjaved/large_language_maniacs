from mpi4py import MPI
from PIL import Image
from skimage import color
import scipy
import sys, os, shutil
import photo_match_labimg as photo_match

def process(pars):   
        
#%% load the parameters that CAN be specified from the command line
    NPlacers = pars['NPlacers']
    NScrapers = pars['NScrapers']
    iters = pars['iters']
    MaxTilesVert = pars['MaxTilesVert']
    per_page = pars['per_page']
    fidelity = pars['fidelity']
    poolSize = pars['poolSize']
    #tags = ('Minimalism',)
    tags = ('Face','Leuven','Belgium','Computer')
    #tags = ('Bussum','Football','PSV','Minimalism','urbex')



#%% MPI stuff
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()
    status = MPI.Status()
#%% print the values of those parameters that CAN be specified via the command line
    for key, value in pars.iteritems():
        print "M{}: {} is now {}".format(rank, key, value)

#%% identify oneself
    #print "Master, process {} out of {}".format(rank, size) 
    print "M{}: > init".format(rank) 

#%% initialize the photo matcher
    pmPars = {'fidelity': fidelity}
    pm = photo_match.photoMatch(pmPars)

    # create empty save-path
    if not pars['useDB']:
        if (os.path.exists(pars['savepath'])):
            shutil.rmtree(pars['savepath'], ignore_errors=True)
        os.mkdir(pars['savepath'])
    
#%% call the scrapers right at the beginning, as it is probably the slowest
    PixPerTile = scipy.array((75,75))
    ComparePixPerTile = scipy.array((fidelity,fidelity))
    scraperPars = {'pm': pm, 'tags': tags, 'PixPerTile': PixPerTile, 'poolSize': poolSize}
    for scraper in range(1,1+NScrapers):
	comm.send(scraperPars, dest=scraper, tag=0)

    TilesVert = int(MaxTilesVert/NPlacers) * NPlacers
    
    TargetImg = Image.open('./Matilda.JPG')
    #TargetImg = Image.open('./rainbow_flag_by_kelly.jpg')
    #TargetImg = Image.open('./korneel_test.jpg')
    TargetSize = TargetImg.size
    TilesHor = (TargetSize[0]*PixPerTile[1]*TilesVert)/(TargetSize[1]*PixPerTile[0])
    Tiles = scipy.array((TilesHor, TilesVert), dtype=int)
    TilesPerNode = scipy.array((TilesHor, TilesVert/NPlacers), dtype=int)
    Pixels        = Tiles*PixPerTile
    ratio = 2.0 / 3.0
    TargetChunkPixels = Tiles*scipy.int_(PixPerTile*ratio)
    ComparePixels = Tiles*scipy.int_(ComparePixPerTile*ratio)
    
#%% adjust the image to have the correct shape (aspect ratio) for turning it into a mosaic
    UnscaledWidth = (TargetSize[1]*Tiles[0])/Tiles[1]# the width of the original size image to yield the correct aspect ratio
    CropMargin = (TargetSize[0] - UnscaledWidth)/2
    #TargetImg.crop((0,0,))
    #TargetImg.resize(Pixels)
    CroppedImg = TargetImg.transform((ComparePixels[0],ComparePixels[1]), Image.EXTENT, (CropMargin,0, CropMargin+UnscaledWidth,TargetImg.size[1]))
    CroppedArr = color.rgb2lab(scipy.array(CroppedImg))

#%% send each placer some parameters
    placerPars = {'TilesPerNode': TilesPerNode, 'UnscaledWidth': UnscaledWidth, 
                  'Tiles': Tiles, 'pm': pm, 'iters': iters, 'PixPerTile': PixPerTile, 'ComparePixPerTile' : ComparePixPerTile}
    for placer in range(NPlacers):
        comm.send(placerPars, dest=1+NScrapers+placer, tag=0)
    print "M{}: < init".format(rank) 
    
    print "M{}: > dividing image".format(rank) 
#%% reduce CroppedArr to NPlacers NodeArrs
    NodeArrs = scipy.split(CroppedArr, NPlacers, axis=0) 

#%% send each of the placers its piece of the picture
    for placer in range(NPlacers):
        comm.send(NodeArrs[placer], dest=1+NScrapers+placer, tag=1)

    #%% create the final image and divide it into pieces for the placers to FinalArr = CroppedArr.copy()
    # now the division has to be accurate!
    FinalArr = scipy.zeros((TargetChunkPixels[1], TargetChunkPixels[0], 3), dtype='i')
    # FinalArr = scipy.zeros((Tiles[1]*PixPerTile[1], Tiles[0]*PixPerTile[0], 3), dtype='i')
    NodeFinalArrs = scipy.split(FinalArr, NPlacers, axis=0)
    print "M{}: < dividing image".format(rank) 
    

#%% listen to the placers' intermediate results
    tempNodeFinalArr = NodeFinalArrs[0].copy() # for receiving the data, before it is known whence it came
    for it in range(iters):
        print "M{}: > not listening to the placer to scraper broadcast".format(rank) 
        dummy_arrs = scipy.zeros((per_page, PixPerTile[1], PixPerTile[0], 3), dtype=scipy.uint8)
        for scraper in range(1, 1+NScrapers):
            #print "M{}: not listening to scraper {}".format(rank, scraper)
            comm.Bcast(dummy_arrs, root=scraper)
        print "M{}: < not listening to the placer to scraper broadcast".format(rank) 
        
        #print "M{}: now listening for placer results at iter {} out of {}".format(rank, it, iters)
        print "M{}: > listening for results".format(rank) 
        for p in range(NPlacers): # listen for the placers
            #print "M{}: NodeFinalArrs[{}] has shape ".format(rank, placer), NodeFinalArrs[placer].shape
            #print "M{}: NodeFinalArrs[{}] has type ".format(rank, placer), type(NodeFinalArrs[placer][0,0,0])
            comm.Recv([tempNodeFinalArr, MPI.INT], source=MPI.ANY_SOURCE, tag=4, status=status)
            placer = status.Get_source()
            NodeFinalArrs[placer-(1+NScrapers)][:,:,:] = tempNodeFinalArr
        print "M{}: < listening for results".format(rank) 
            
        print "M{}: > writing image".format(rank) 
        FinalImg = Image.fromarray(scipy.array(FinalArr, dtype=scipy.uint8), 'RGB')
        FinalImg.save('output/mosaic_{}.png'.format(it)) # for fewer output images
        print "M{}: < writing image at iter {}".format(rank, it) 
    del(pars['savepath'])
    strrep = '_'.join(['{}{:d}'.format(item, value) for item, value in sorted(pars.items())])+'.png'
    FinalImg.save('output/final'+strrep)
    print "M{}: Final image saved".format(rank)
    shutil.copy('log', 'output/log_'+strrep)

#%% signal completion
    comm.barrier()
    print "M{}: reached the end of its career".format(rank)
