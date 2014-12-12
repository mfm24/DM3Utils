import os
from tempfile import mkstemp

from parse_dm3_grammar import parse_dm_header

from dm3_image_utils import imagedatadict_to_ndarray
import array
# mfm 2014-02-04 would like ability to flip through using arrow keys
# we had this flag in ParseDM3File, but it's been removed.
# ParseDM3File now only returns arrays or structarrays and doesn't rely
# on numpy. Structarrays are not amenable to being acted on as lists
# but I'm not sure numpy provides any really significant functions either
# (excpet histogram, I guess). Let's rely on it for now
use_numpy_arrays = True


try:
    import numpy as np
    immin = lambda x: x.min()
    immax = lambda x: x.max()
    hist_func = np.histogram
except ImportError:
    hist_func = None

try:
    import PIL.Image
    has_pil = True
except ImportError:
    has_pil = False

if not hist_func:
    def my_hist(im, bins, range):
        ret = [0]*bins
        binstep = 1.0*bins/(range[1]-range[0])
        for p in im:
            bini = int(binstep*(p-range[0]))
            if bini > 0 and bini < bins:
                ret[bini] += 1
        return ret, None

    immin = lambda x: min(x)
    immax = lambda x: max(x)
    hist_func = my_hist


# Some helper functions
def nparray_to_pgm(stream_out, im, shape):
    """
    Convert the im array with shape shape to a PGM string
    writes it into the stream_out stream.
    """
    stream_out.write("P5\n")  # P5 is binary grayscale
    stream_out.write("%d %d\n" % (shape[0], shape[1]))  # dimensions
    stream_out.write("255\n")
    if use_numpy_arrays:
        stream_out.write(np.asarray(im, dtype=np.uint8))
    else:
        out = array.array('B')
        out.extend((int(min(255, max(0, x))) for x in im))
        stream_out.write(out)


def get_image(dmtag, num):
    im = dmtag['ImageList'][num]['ImageData']['Data']
    with open("dmout.pgm", 'wb') as f:
        nparray_to_pgm(f, im.flatten()/32767, im.shape)


from Tkinter import *
import tkFileDialog

class DM3Loader(object):
    """
    A loader should be calable with a path and return an nd
    image. It should have a extensions property that returns a list of
    acceptable extensions for the file
    """
    def __call__(self, path):
        with open(path, "rb") as f:
            op = parse_dm_header(f)
        return imagedatadict_to_ndarray(
            op['ImageList'][-1]['ImageData'])

    @property
    def extensions(self):
        return ['dm3', 'dm4']

class FolderImageSource(object):
    """
    A source simply has to expose a next(steps) function that will initially
    get called with 0.
    """
    def __init__(self, path, loaders):
        self.path = path
        self.loaders = loaders

    @staticmethod
    def get_extension(path):
        return os.path.splitext(path)[1][1:]

    def get_image_and_title(self):
        ext = self.get_extension(self.path)
        for l in self.loaders:
            if ext in l.extensions:
                return l(self.path), os.path.basename(self.path)

    def next(self, delta):
        if delta != 0:
            path, name = os.path.split(self.path)
            # if path is blank use '.'
            path = path or "."
            all_exts = [x for loader in self.loaders for x in loader.extensions]
            names = [x for x in os.listdir(path)
                     if self.get_extension(x) in all_exts]
            print "New image from ", self.path,
            newname = names[(names.index(name) + delta) % len(names)]
            self.path = os.path.join(path, newname)
            print "to", self.path
        return self.get_image_and_title()



class ImageCanvas(Canvas):
    def __init__(self, source, limits=None, root=None):
        self.source = source
        if not root:
            root = Tk()
        self.root = root
        self.photoimage = self.tkimage = None
        self.histimage = None
        self.arr = None
        Canvas.__init__(self, self.root, width=1, height=1)
        self.pack()
        self.limits = limits or {}
        self.root.bind_all("<Left>", lambda e: self.next_image(1))
        self.root.bind_all("<Right>", lambda e: self.next_image(-1))
        self.root.bind_all("<Escape>", lambda e: quit())
        if has_pil:
            menubar = Menu(self.root)
            file_menu = Menu(menubar, tearoff=0)
            file_menu.add_command(label="Save As...", command=self.save_im)
            menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)
        self.next_image(0)
        root.mainloop()
        # copied some from demo/tkinter/guido/imagedraw.py
        # unfortunately PhotoImage only accepts base64 encoded GIF files
        # while we can specify a PGM filename. We create a temporary file
        # as a workaround

    def clip_im(self, nparr):
        h, w = nparr.shape
        lo, hi = self.limits
        scale = 255.0 / (hi - lo)
        off = lo
        if use_numpy_arrays:
            return np.clip(scale * (nparr - off), 0, 255).astype(np.uint8)
        else:
            return map(lambda x: int(scale*(x-off)), nparr)

    @staticmethod
    def make_photoimageim(nparr):
        h, w = nparr.shape
        f, fname = mkstemp()
        try:
            os.close(f)
            with open(fname, "wb") as f:
                nparray_to_pgm(f, nparr, (w, h))
            img = PhotoImage(file=fname)
        finally:
            os.remove(fname)
        return img

    def save_im(self):
        """save newim to user specified file"""
        opts = {'defaultextension': '.png',
                'filetypes': [('all files', '.*'), ('PNG Files', '.png')],
                }
        f = tkFileDialog.asksaveasfilename(**opts)
        if f:
            PIL.Image.fromarray(self.clip_im(self.arr)).save(f)

    def new_limits(self, new_limits):
        self.limits=new_limits
        if self.tkimage is not None:
            self.delete(self.tkimage)
        npimage = self.clip_im(self.arr)
        # we need to keep a reference to the photoimage
        self.photoimage = self.make_photoimageim(npimage)
        self.tkimage = self.create_image(0, 1, anchor=NW,
                                          image=self.photoimage)
        if self.histimage:
            self.histimage.destroy()
        self.histimage = create_histogram(self.arr,
                                           self.root, 128, self.limits,
                                           self.new_limits)
        self.histimage.place(anchor=NW)

    # we look for arrow keys..
    def next_image(self, step):
        im, title = self.source.next(step)
        self.arr = im
        self.root.wm_title(title)
        h, w = self.arr.shape
        self.config(width=w, height=h + 1)  # resize existing canvas
        limits = (immin(self.arr), immax(self.arr))
        self.new_limits(limits)


def create_histogram(im, tkroot, size, limits, rangechangefunc):

    def add_hist_to_photoimage(im, out_pim, back="#D0D0D0", fore="#A0A0DD"):
        """
        For the image im, calculates a histogram and puts it into the supplied
        PhotoImage, out_pim
        """
        hist_width, hist_height = out_pim.width(), out_pim.height()
        vals, bins = hist_func(im, bins=hist_width,
                               range=limits)
        # we now create the image
        # we show 0 to vals.max() in hist_height steps
        pics = ""
        for j in range(hist_height, 0, -1):
            lim = immax(vals) * 1.2 * j / hist_height
            pics += ("{"
                     + " ".join(back if x < lim else fore for x in vals)
                     + "} ")
        out_pim.put(pics)

    hist = PhotoImage(width=size, height=size)
    add_hist_to_photoimage(im, hist)
    canv_hist = Canvas(tkroot, width=size, height=size)
    canv_hist.create_image(0, 0, anchor=NW, image=hist)
    clickstuff = {}

    def start_click(e):
        if "box" in clickstuff:
            canv_hist.delete(clickstuff["box"])
        clickstuff["start"] = e.x
        clickstuff["box"] = canv_hist.create_rectangle(
            (clickstuff["start"], 0, clickstuff["start"], size))

    def move_click(e):
        if "box" in clickstuff:
            canv_hist.delete(clickstuff["box"])
            clickstuff["box"] = canv_hist.create_rectangle(
                (clickstuff["start"], 0, e.x, size))

    def end_click(e):
        if "box" in clickstuff:
            canv_hist.delete(clickstuff["box"])
            if clickstuff["start"] != e.x:
                low = 1.0 * min(e.x, clickstuff["start"]) / size
                high = 1.0 * max(e.x, clickstuff["start"]) / size
                full_range = limits[1] - limits[0]
                rangechangefunc((limits[0] + low * full_range,
                                limits[0] + high * full_range))

    def reset_click(e):
        rangechangefunc((immin(im), immax(im)))

    canv_hist.bind("<Button-1>", start_click)
    canv_hist.bind("<B1-Motion>", move_click)
    canv_hist.bind("<ButtonRelease-1>", end_click)
    canv_hist.bind("<Double-Button-1>", reset_click)
    canv_hist.img = hist
    return canv_hist


def show_dm_image_script():
    # setup.py script entry for showing images
    import sys
    ImageCanvas(FolderImageSource(sys.argv[1], [DM3Loader()]))

if __name__ == '__main__':
    import sys
    action = "showimage"  # the default
    file = None
    if len(sys.argv) > 2:
        action = sys.argv[1]
        file = sys.argv[2]
    elif len(sys.argv) > 1:
        file = sys.argv[1]
    else:
        print ("Arguments are [Action] File."
               " Action can be one of 'showimage', "
               "'listdispersions', 'countdispersions', 'imageinfo'")
    if file:
        print file, action
        with open(file, "rb") as f:
            op = parse_dm_header(f)
        if action == "showimage":
            # arr = imagedatadict_to_ndarray(op['ImageList'][-1]['ImageData'])
            ImageCanvas(FolderImageSource(file, [DM3Loader()]))
        elif action == "listdispersions":
            for kvlist in op["PrimaryList"]:
                print "Energy %lf has dispersions:" % kvlist['Prism']['Energy']
                for disp in kvlist["DispersionList"]["List"]:
                    print "\t%lf" % disp['Dispersion']
                print
        elif action == "countdispersions":
            for kvlist in op["PrimaryList"]:
                print "Energy %lf has %d dispersions" % (
                    kvlist['Prism']['Energy'],
                    len(kvlist["DispersionList"]["List"]))
        elif action == "imageinfo":
            for i, image in enumerate(op["ImageList"]):
                print ("Image %d: %s,"
                       " PixelDepth: %d,"
                       " DataType: %d "
                       "(converted type %s)") % (
                    i, image["ImageData"]["Dimensions"],
                    image["ImageData"]["PixelDepth"],
                    image["ImageData"]["DataType"],
                    type(image["ImageData"]["Data"])
                    )
