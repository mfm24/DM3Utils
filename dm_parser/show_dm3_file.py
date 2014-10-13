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


def show_image(filepath, limits=None):
    # copied some from demo/tkinter/guido/imagedraw.py
    # unfortunately PhotoImage only accepts base64 encoded GIF files
    # while we can specify a PGM filename. We create a temporary file
    # as a workaround
    show_image.filepath = filepath
    limits = {}
    root = Tk()
    root.wm_title(os.path.split(filepath)[1])

    def clip_im(nparr):
        h, w = nparr.shape
        scale = 255.0 / (limits['high'] - limits['low'])
        off = limits['low']
        if use_numpy_arrays:
            return np.clip(scale * (nparr - off), 0, 255).astype(np.uint8)
        else:
            return map(lambda x: int(scale*(x-off)), nparr)

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

    def save_im():
        """save newim to user specified file"""
        opts = {'defaultextension': '.png',
                'filetypes': [('all files', '.*'), ('PNG Files', '.png')],
                }
        f = tkFileDialog.asksaveasfilename(**opts)
        if f:
            PIL.Image.fromarray(canv._npimage).save(f)

    canv = Canvas(root, width=1, height=1)
    canv._npimage = canv._photoimage = canv._tkimage = None
    canv._histimage = None
    canv.pack()

    def new_limits(low, high):
        limits['low'] = low
        limits['high'] = high
        if canv._tkimage is not None:
            canv.delete(canv._tkimage)
        canv._npimage = clip_im(show_image.arr)
        canv._photoimage = make_photoimageim(canv._npimage)
        canv._tkimage = canv.create_image(0, 1, anchor=NW,
                                          image=canv._photoimage)
        if canv._histimage:
            canv._histimage.destroy()
        canv._histimage = create_histogram(show_image.arr,
                                           root, 128, limits, new_limits)
        canv._histimage.place(anchor=NW)

    # we look for arrow keys..
    def next_image(step):
        if step != 0:
            path, name = os.path.split(show_image.filepath)
            # if path is blank use '.'
            path = path or "."
            names = [x for x in os.listdir(path)
                     if os.path.splitext(x)[1] in [".dm3", ".dm4"]]
            print "New image from ", show_image.filepath,
            newname = names[(names.index(name) + step) % len(names)]
            show_image.filepath = os.path.join(path, newname)
            root.wm_title(newname)
            print "to", show_image.filepath
        # reload the image, could be nicer here...
        with open(show_image.filepath, "rb") as f:
            op = parse_dm_header(f)
        show_image.arr = imagedatadict_to_ndarray(
            op['ImageList'][-1]['ImageData'])
        h, w = show_image.arr.shape
        canv.config(width=w, height=h + 1)  # resize existing canvas
        limits = dict(low=immin(show_image.arr), high=immax(show_image.arr))
        new_limits(limits['low'], limits['high'])

    root.bind_all("<Left>", lambda e: next_image(1))
    root.bind_all("<Right>", lambda e: next_image(-1))
    root.bind_all("<Escape>", lambda e: quit())

    if has_pil:
        menubar = Menu(root)
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save As...", command=save_im)
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)

    next_image(0)
    root.mainloop()

def create_histogram(im, tkroot, size, limits, rangechangefunc):

    def add_hist_to_photoimage(im, out_pim, back="#D0D0D0", fore="#A0A0DD"):
        """
        For the image im, calculates a histogram and puts it into the supplied
        PhotoImage, out_pim
        """
        hist_width, hist_height = out_pim.width(), out_pim.height()
        vals, bins = hist_func(im, bins=hist_width,
                               range=(limits["low"], limits['high']))
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
                full_range = limits['high'] - limits['low']
                rangechangefunc(limits['low'] + low * full_range,
                                limits['low'] + high * full_range)

    def reset_click(e):
        rangechangefunc(immin(im), immax(im))

    canv_hist.bind("<Button-1>", start_click)
    canv_hist.bind("<B1-Motion>", move_click)
    canv_hist.bind("<ButtonRelease-1>", end_click)
    canv_hist.bind("<Double-Button-1>", reset_click)
    canv_hist.img = hist
    return canv_hist


def show_dm_image_script():
    # setup.py script entry for showing images
    import sys
    show_image(sys.argv[1])


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
            show_image(file)
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
