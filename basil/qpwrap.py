#!/usr/bin/env python
"""
Workspace and Image implementations for Quantiphyse
"""

import os
import sys
import shutil
import shlex
import subprocess
import errno
import tempfile
import collections
import re

import nibabel as nib
import numpy as np

        self.fpath = os.path.join(self.dpath, self.fname)
        return self

    def _guess_extension(self):
        """
        Guess the extension of the file, if the name was given without extension
        
        Looks for already existing files with the same ipath and a Nifti extension.
        The attribute ``ext_matches`` stores the matching extensions. If no matches
        are found, the default Nifti extension is set (``.nii.gz``)
        """
        exts = ["", ".nii", ".nii.gz"]
        self.ext_matches = []
        for ext in exts:
            if os.path.exists("%s%s" % (self.ipath, ext)):
                self.ext_matches.append(ext)

        if self.ext_matches:
            self.ext = self.ext_matches[0]

    def data(self):
        """
        Return the image data

        If image was initialized from a file and has not yet been loaded, this
        will load the data from the file.

        :returns: A Numpy array of image data
        """
        if self._data is None:
            self._data = self.nii.get_data()
        return self._data

    def summary(self, log=sys.stdout):
        """
        Output a readable summary of the image

        :param log: File or output stream to write to (default: sys.stdout)
        """
        log.write("%s: %s\n" % (self.role.ljust(30), self.iname))
        log.write("Full path                     : %s\n" % self.fpath)

    def check_shape(self, shape):
        """
        Check that image shape matches another shape

        :param shape: Shape to check against
        """
        if len(self.shape) != len(shape):
            raise ValueError("%s: expected %i dims, got %i" % (self.file_type, len(shape), len(self.shape)))
        if self.shape != shape:
            raise ValueError("%s: shape (%s) does not match (%s)" % (self.file_type, str(self.shape), str(shape)))

    def derived(self, data, name=None, suffix=None, **kwargs):
        """
        Create a derived image based on this one, but with different data

        Useful because it preserves orientation info, etc
        May be overridden in subclasses to preserve subclass-specific attributes

        :param data: Numpy data for derived image
        :param name: Name for new image (can be simple name or full filename)
        :param suffix: If name not specified, construct by adding suffix to original image name

        Any further keyword parameters are passed to the Image constructor
        """
        if name is None and suffix is None:
            name = self.ipath
        elif name is None:
            name = self.ipath + suffix
        return Image(name, data=data, base=self, **kwargs)

class Workspace(object):
    """
    A workspace for FSL processing

    Based on a working directory, which may be temporary or persistent.
    """

    FILENAME = 1
    IMAGE = 2
    NUMPY = 3

    def __init__(self, workdir=None, log=sys.stdout, imgs=(), path=None, debug=False, echo=False, use_local_dir=True):
        """
        Create workspace

        :param workdir: If specified, use this path for the working directory. Will be created
        if not already existing
        :param log: File stream to write log output to (default: sys.stdout)
        :param imgs: List of Image object which will be save to working directory
        :param path: Optional list of directories to search for binaries. If not specified, will
        look in $FSLDEVDIR/bin, $FSLDIR/bin
        :param debug: If True, enable debugging messages
        :param echo: If True, echo commands and their output to the log
        :param use_local_dir: If True, use the directory of the calling program (sys.argv[0])
        as the first entry in the binary search path. This is enabled by default because
        it gives a useful way for scripts to replace standard FSL programs with their own copies
        by putting them in the same directory as the script.
        """
        if workdir is not None:
            self.workdir = os.path.abspath(workdir)
            mkdir(workdir)
            self.is_temp = False
        else:
            self.workdir = tempdir("fsl")
            self.is_temp = True
        
        for img in imgs:
            self.add_img(img)

        if path is None:
            path = []
            if use_local_dir:
                path.append(os.path.dirname(os.path.abspath(sys.argv[0])))
            for env_var in ("FSLDEVDIR", "FSLDIR"):
                if env_var in os.environ:
                    path.append(os.path.join(os.environ[env_var], "bin"))
        self._path = path
        self.log = log
        self.debug_enabled = debug
        self.echo_enabled = echo
        
        if "FSLOUTPUTTYPE" not in os.environ:
            os.environ["FSLOUTPUTTYPE"] = "NIFTI_GZ"

    def __del__(self):
        if self.is_temp:
            shutil.rmtree(self.workdir)

    def echo(self, *args, **kwargs):
        """
        Echo command or command output to log

        Only occurs if echo is enabled on workspace
        """
        if self.echo_enabled:
            self.log.write(*args, **kwargs)
            self.log.write("\n")

    def debug(self, *args, **kwargs):
        """
        Send debug message to log

        Only occurs if debug is enabled on workspace
        """
        if self.debug_enabled:
            self.log.write(*args, **kwargs)
            self.log.write("\n")

    def add_img(self, img, name=None):
        """
        Save an image to the workspace

        :param img: Image object. It will be saved in the workspace and its filepath modified
        """
        if name is None:
            name = img.fname
        img.save(os.path.join(self.workdir, name))

    def add_file(self, fpath, name=None):
        """
        Add a random named file to the workspace
        """
        if name is None:
            name = os.path.basename(fpath)
        shutil.copyfile(fpath, os.path.join(self.workdir, name))

    def add_text(self, text, name):
        """
        Write a text file to the workspace

        :param text: Text to put in the file
        :param name: File name
        """
        with open(os.path.join(self.workdir, name), "w") as tfile:
            tfile.write(text)

    def del_img(self, img):
        """
        Delete an image from the workspace
        """
        try:
            image, _ = self._input_img(img)
            os.remove(image.fpath)
        except IOError:
            self.log.write("WARNING: failed to delete %s\n" % img)

    def sub(self, name, imgs=()):
        """
        Create a sub-workspace, (i.e. a subdir of this workspace)

        This inherits the log output from the parent workspace

        :param name: Name of subdir
        :imgs imgs: Images to copy to the sub workspace
        """
        return Workspace(os.path.join(self.workdir, name), imgs=imgs, log=self.log, echo=self.echo_enabled,
                         debug=self.debug_enabled)

    def run(self, prog, args="", expected=()):
        """
        Run an FSL program

        This is used to run FSL programs for which wrappers have not yet been provided

        :param prog: Name of program to run
        :param args: Command line arguments, either as a string or as a dictionary
                     (in which case argument will be passed as 'key value')
        :param expected: List of expected output items (images or text files). If none 
                         are specified, all modified files in the workspace are returned
        :return Tuple of (Image instances, text file names, command stdout)
        """
        cwd = os.getcwd()
        try:
            os.chdir(self.workdir)

            # Build command line arguments from prog and args
            cmd = self._find(prog)
            if isinstance(args, dict):
                for arg, value in args.items():
                    cmd += " %s " % arg
                    if value is not None and value != "": 
                        cmd += str(value)
            else:
                cmd = cmd + " " + args
            self.echo(cmd)

            # Find out what files were in the workspace before this command
            pre_run_files = self._get_files()
            #self.debug("Pre run: %s" % str(pre_run_files))

            # Run the command
            p = subprocess.Popen(shlex.split(cmd), stdout=self.log, stderr=subprocess.STDOUT, bufsize=1)
            retcode = p.wait()
            if retcode != 0:
                raise RuntimeError("Command '%s': Non-zero output status: %i" % (cmd, retcode))
                
            # Find out what files were in the workspace after this command
            # and turn them into images or text files are required
            post_run_files = self._get_files()
            #self.debug("Post run: %s" % str(post_run_files))
            imgs, text = self._get_return_files(pre_run_files, post_run_files, expected)

            return imgs, text
        finally:
            os.chdir(cwd)

    def bet(self, img, **kwargs):
        """
        FSL Brain Extraction Tool

        :param img: Input whole head image
        :return Tuple of Brain extracted image and brain mask image
        """
        img, itype = self._input_img(img)
        output_name, args = self._get_std(img, "_bet", kwargs)
        mask = kwargs.pop("mask", False)
        brain = kwargs.pop("brain", True)
        args = "%s %s %s" % (img.ipath, output_name, args)
        if mask: args += " -m"
        if not brain: args += " -n"
        imgs, _ = self.run("bet", args=args, expected=[output_name, output_name + "_mask"])
        ret = [self._output_img(i, itype) for i in imgs]
        if len(ret) == 1:
            return ret[0]
        return tuple(ret)

    def fabber(self, model_group, img, mask, options, overwrite=True, **kwargs):
        """
        Fabber model fitting

        :param img: Input image
        :param mask: Mask image
        :return: MVN output image
        """
        img, itype = self._input_img(img)
        mask, _ = self._input_img(mask)
        output_name, extra_args = self._get_std(img, "_fabber", kwargs)

        options = dict(options)
        options["data"] = img.ipath
        options["mask"] = mask.ipath
        options["output"] = output_name
        options["save-mvn"] = ""
        if overwrite:
            options["overwrite"] = ""
        option_args = ""
        for k, v in options.items():
            if v == "" or v == True:
                option_args += " --%s" % k
            elif v:
                option_args += " --%s=%s" % (k, str(v))

        args = "%s %s" % (option_args, extra_args)
        imgs, _ = self.run("fabber_%s" % model_group.lower(), args=args, expected=[output_name + "/finalMVN"])
        return self._output_img(imgs[0], itype)

    def fast(self, img, **kwargs):
        """
        FSL Segmentation Tool

        :param img: Input structural image
        :return Segmented image
        """
        img, itype = self._input_img(img)
        output_name, args = self._get_std(img, "_fast", kwargs)
        args = "-o %s %s %s" % (output_name, args, img.ipath)

        imgs, _ = self.run("fast", args=args, expected=[output_name + "_seg"])
        return self._output_img(imgs[0], itype)

    def flirt(self, img, ref, **kwargs):
        """
        FSL Linear Registration Tool

        :param img: Input image
        :param ref: Reference image
        :return Registered image. If output_mat=True, also return transformation matrix. 
                If output_invmat=True, also return inverse transformation matrix
        """
        img, itype = self._input_img(img)
        ref, _ = self._input_img(ref)
        output_name, args = self._get_std(img, "_reg", kwargs)
        args = "-in %s -ref %s -out %s %s" % (img.ipath, ref.ipath, output_name, args)

        expected = [output_name]
        output_mat = kwargs.pop("output_mat", None)
        output_invmat = kwargs.pop("output_invmat", None)
        if output_mat is not None or output_invmat is not None:
            args += " -omat %s" % output_mat
            expected.append(output_mat)

        imgs, files = self.run("flirt", args=args, expected=expected)

        ret = [self._output_img(imgs[0], itype),]
        if output_mat is not None:
            ret.append(text_to_matrix(files[output_mat]))
        if output_invmat is not None:
            invmat = np.linalg.inv(text_to_matrix(files[output_mat]))
            self.add_text(matrix_to_text(invmat), output_invmat)
            ret.append(invmat)
        if len(ret) == 1:
            return ret
        return tuple(ret)
        
    def apply_xfm(self, img, ref, xfm, **kwargs):
        """
        Apply linear transformation to an image

        :param img: Input image
        :param ref: Reference image
        :param xfm: Transformation matrix. May be a filename or an Numpy array
        :return Transformed image.
        """
        img, itype = self._input_img(img)
        xfm, _ = self._input_matrix(xfm)
        output_name, args = self._get_std(img, "_reg", kwargs)
        args = "-in %s -ref %s -applyxfm -init %s -out %s %s" % (img.iname, ref.iname, xfm, output_name, args)
        imgs, _ = self.run("flirt", args=args, expected=[output_name], **kwargs)
        return self._output_img(imgs[0], itype)

    def mcflirt(self, img, cost=None, ref=None, **kwargs):
        """
        FSL motion correction tool

        :param img: 4D Input image
        :param cost: Cost model (default = normalized correlation)
        :param ref: Optional reference image. If not specified, taken from input image
        :return Motion corrected image
        """
        img, itype = self._input_img(img)
        output_name, args = self._get_std(img, "_mc", kwargs)
        args = "-in %s -out %s %s" % (img.ipath, output_name, args)
        if cost is not None:
            args += " -cost %s" % cost
        if ref is not None:
            ref, _ = self._input_img(ref)
            args += " -r %s" % ref.ipath
        imgs, _ = self.run("mcflirt", args=args, expected=[output_name])
        return self._output_img(imgs[0], itype)

    def maths(self, img, *args, **kwargs):
        """
        Generic FSL mathematical operations on images

        :param img: 4D Input image
        :param args: Command line arguments to fslmaths, e.g. '-mul 2 -uthr 7'
        :return Output image
        """
        img, itype = self._input_img(img)
        self.echo_enabled = True
        output_name, args = self._get_std(img, "_maths", kwargs)
        args = "%s %s %s" % (img.ipath, args, output_name)
        imgs, _ = self.run("fslmaths", args=args, expected=[output_name])
        return self._output_img(imgs[0], itype)

    def imcp(self, src, dest):
        """
        Image copy

        Note that this should not really be needed. 
        """
        args = "%s %s" % (src.ipath, dest.ipath)
        self.run("imcp", args=args)
    
    def _input_img(self, img):
        """
        Handle input images which may be given as
          - strings, interpreted as file name in working dir
          - Image instances
          - Numpy arrays
        
        Note that care is required with Numpy arrays because they have no
        orientation or grid information which some FSL programs may require.
        """
        if isinstance(img, Image):
            return img, self.IMAGE
        elif isinstance(img, basestring):
            return Image(img), self.FILENAME
        elif isinstance(img, np.ndarray):
            tempf = tempfile.NamedTemporaryFile(dir=self.workdir, prefix="fsl", delete=False)
            tempname = tempf.name
            tempf.close()
            return Image(tempname, data=img, save=True), self.NUMPY
        else:
            raise TypeError("Image data not recognized - must be filename, Image instance or Numpy array")

    def _input_matrix(self, mat):
        """
        Handle input matrices which may be given as
          - strings, interpreted as file name in working dir
          - Numpy arrays
        
        Note that care is required with Numpy arrays because they have no
        orientation or grid information which some FSL programs may require.
        """
        if isinstance(mat, basestring):
            return mat, self.FILENAME
        elif isinstance(mat, np.ndarray):
            tempf = tempfile.NamedTemporaryFile(dir=self.workdir, prefix="fsl", suffix=".mat", delete=False)
            fname = tempf.name
            tempf.close()
            self.add_text(matrix_to_text(mat), os.path.basename(fname))
            return fname, self.NUMPY
        else:
            raise TypeError("Matrix data not recognized - must be filename or Numpy array")

    def _output_img(self, img, itype):
        """
        Return output image as the requested type:
          - Workspace.FILENAME returned as an absolute path
          - Workspace.IMAGE returned as Image instance
          - Workspace.NUMPY returned as Numpy array
        """
        if itype == self.IMAGE:
            return img
        elif itype == self.FILENAME:
            return img.fpath
        elif itype == self.NUMPY:
            return img.data()
        else:
            raise TypeError("Image type not recognized - must be filename, Image instance or Numpy array")

    def _get_std(self, img, suffix, kwargs):
        """
        Return standard keyword arguments, output_name and args. Output name is derived
        from img and suffix if not specified
        """
        return kwargs.pop("output_name", img.iname + suffix), kwargs.pop("args", "")

    def _find(self, cmd):
        """ 
        Find a program in the configured path
        """
        for dname in self._path:
            ex = os.path.join(dname, cmd)
            if os.path.isfile(ex) and os.access(ex, os.X_OK):
                return ex
        
        return cmd

    def _get_files(self, workdir=None):
        """
        Get a dict of filename : modification time for the files in working directory
        """
        if workdir is None:
            workdir = self.workdir
        dir_files = {}
        for _, dirnames, files in os.walk(workdir):
            for fname in files:
                fname = os.path.relpath(os.path.join(workdir, fname), self.workdir)
                if os.path.isfile(fname):
                    dir_files[fname] = os.path.getmtime(fname)
            for dirname in dirnames:
                dir_files.update(self._get_files(os.path.join(workdir, dirname)))
        return dir_files
   
    def _changed_files(self, pre, post):
        """
        Return list of files which have changed between pre and post (expected to 
        be outputs of _get_files)
        """
        self.debug("Post: %s" % str(post))
        changed_files = []
        for f, mtime in post.items():
            if f not in pre or mtime > pre[f]:
                changed_files.append(f)

        self.debug("Changed files: %s" % str(changed_files))
        return changed_files

    def _get_return_files(self, pre, post, expected):
        """
        Get the files to return from a command

        If expected is non-empty then only return expected files. Expected
        contains file basenames only (e.g. 'data_mc' would return 'data_mc.nii.gz')

        If expected is empty, return all changed files
        """
        #self.debug("Expected: %s" % str(expected))
        return_files = []
        if expected:
            for fname in post:
                for exp in expected:
                    if re.match(exp, fname):
                        return_files.append(fname)
        else:
            return_files = self._changed_files(pre, post)

        imgs, text = [], {}
        for fname in return_files:
            try:
                imgs.append(Image(fname))
            except:
                try:
                    text[os.path.basename(fname)] = self._read_text_file(fname)
                except:
                    self.log.write("WARNING: Could not handle output file %s\n" % fname)
                    raise
        return imgs, text

    def _read_text_file(self, fname):
        with open(fname, "r") as f:
            return f.read()

def matrix_to_text(mat):
    """
    Convert matrix array to text using spaces/newlines as col/row delimiters
    """
    rows = []
    for row in mat:
        rows.append(" ".join([str(v) for v in row]))
    return "\n".join(rows)

def text_to_matrix(text):
    """
    Convert space or comma separated file to matrix
    """
    fvals = []
    ncols = -1
    lines = text.splitlines()
    for line in lines:
        # Discard comments
        line = line.split("#", 1)[0].strip()
        # Split by commas or spaces
        vals = line.replace(",", " ").split()
        # Ignore empty lines
        if not vals: continue
        # Check correct number of columns
        if ncols < 0: ncols = len(vals)
        elif len(vals) != ncols:
            raise ValueError("File must contain a matrix of numbers with fixed size (rows/columns)")
        # Check all data is numeric
        for val in vals:
            try:
                float(val)
            except:
                raise ValueError("Non-numeric value '%s' found in matrix text" % val)
        fvals.append([float(v) for v in vals])     
    return np.array(fvals)

def mkdir(dirname, fail_if_exists=False, warn_if_exists=True):
    """
    Create a directory, including necessary subdirs
    """
    try:
        os.makedirs(dirname)
    except OSError as e:
        if e.errno == errno.EEXIST:
            if fail_if_exists: raise
            elif warn_if_exists: print("WARNING: mkdir - Directory %s already exists" % dirname)
    return os.path.abspath(dirname)

def tempdir(suffix, debug=False):
    """
    Create a temporary directory

    :param debug: If True, creates directory in current working directory
    """
    if debug:
        tmpdir = os.path.join(os.getcwd(), "tmp_%s" % suffix)
        mkdir(tmpdir)
    else:
        tmpdir = tempfile.mkdtemp("_%s" % suffix)
    return tmpdir

def _grab_temp_data(data):
    """
    Recursively look through some command output data, identify
    Image instances and load data into memory.

    This is so output files from temporary workspaces can be 
    returned to the caller with data intact

    We also remove the temporary path from the image file name
    """
    if isinstance(data, collections.Sequence) and not isinstance(data, basestring):
        for d in data:
            _grab_temp_data(d)
    else:
        if isinstance(data, Image):
            data.dpath = ""
            data.ipath = data.iname
            data.fpath = data.fname
            data.data()

def _temp_wrapper(prog):
    """
    Wrap a command in a temporary workspace
    """
    def wrapper(*args, **kwargs):
        wsp = Workspace()
        f = getattr(wsp, prog)
        ret = f(*args, **kwargs)
        _grab_temp_data(ret)
        return ret
    return wrapper

maths = _temp_wrapper("maths")
roi = _temp_wrapper("roi")
stats = _temp_wrapper("stats")
merge = _temp_wrapper("merge")
fast = _temp_wrapper("fast")
bet = _temp_wrapper("bet")
flirt = _temp_wrapper("flirt")
mcflirt = _temp_wrapper("mcflirt")
apply_xfm = _temp_wrapper("apply_xfm")
run = _temp_wrapper("run")
