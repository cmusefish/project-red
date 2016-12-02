"""
code_our_version.py

"""

import numpy as np
import numpy.linalg as npl
import nibabel as nib

from scipy.ndimage import affine_transform, measurements
from scipy.optimize import fmin_powell

from fmri_utils.registration.shared import get_data_affine
from fmri_utils.func_preproc.rotations import x_rotmat, y_rotmat, z_rotmat

def resample(static_data, moving_data, static_affine, moving_affine):
    """ resample moving image in static image space

    Parameters
    ----------
    static_data : array shape (I, J, K)
        array with 3D data from static image

     moving_data : array shape (I, J, K)
        array with 3D data from moving image

    static_affine : array shape (4, 4)
        affine for static image

    moving_affine : array shape (4, 4)
        affine for moving image

    Returns
    -------
    moving_in_stat : array shape (I, J, K)
        array with 3D from moving image resampled in static image space


    """

    moving2static = npl.inv(moving_affine).dot(static_affine)
    mat, vec = nib.affines.to_matvec(moving2static)

    moving_in_stat = affine_transform(moving_data, mat, vec, output_shape=static_data.shape, order=1)

    return moving_in_stat


def transform_cmass(static_data, moving_data, static_affine, moving_affine):
    """ get moving image affine, to use when resampling moving in static space
        --> matches center of mass of moving image to static image (in ref space)

    Parameters
    ----------
    static_data : array shape (I, J, K)
        array with 3D data from static image

    moving_data : array shape (I, J, K)
        array with 3D data from moving image

    static_affine : array shape (4, 4)
        affine for static image

    moving_affine : array shape (4, 4)
        starting affine for mvoing image

    Returns
    -------
    updated_moving_affine : array shape (4, 4)
        new affine for moving image to ref

    """

    static_mat, static_vec = nib.affines.to_matvec(static_affine)
    moving_mat, moving_vec = nib.affines.to_matvec(moving_affine)

    static_cmass = np.array(measurements.center_of_mass(np.array(static_data)))
    moving_cmass = np.array(measurements.center_of_mass(np.array(moving_data)))

    static_cmass_in_ref = static_mat.dot(static_cmass) + static_vec
    moving_cmass_in_ref = moving_mat.dot(moving_cmass) + moving_vec

    diff_cmass_in_ref = static_cmass_in_ref - moving_cmass_in_ref

    shift = nib.affines.from_matvec(np.eye(3), diff_cmass_in_ref)
    updated_moving_affine = shift.dot(moving_affine)

    return updated_moving_affine


def transform_rigid(static_data, moving_data, static_affine, moving_affine, iter, partial=0):
    """ get moving image affine, to use when resampling moving in static space
        --> does rigid (3 trans, 3 rot) alignment, max "iter" iterations

    Parameters
    ----------
    static_data : array shape (I, J, K)
        array with 3D data from static image

    moving_data : array shape (I, J, K)
        array with 3D data from moving image

    static_affine : array shape (4, 4)
        affine for static image

    moving_affine : array shape (4, 4)
        starting affine for static moving

    iter : int
        max number iterations in optimization

    partial : int, flag
        0 = find best tranlation, then find best rotations
        1 = find best translation only
        2 = find best rotation only

    Returns
    -------
    updated_moving_affine : array shape (4, 4)
        new affine for moving image to ref

    """

    def MI_cost_translation(translations):
        ## cost function for translations using MI
        #create affine from new params
        shift_affine = nib.affines.from_matvec(np.eye(3), translations)
        updated_moving_affine = moving_affine.dot(shift_affine)

        #resample with new affine
        moving_resampled = resample(static_data, moving_data, static_affine, updated_moving_affine)

        #get negative mutual information (static & new moving)
        neg_MI = (-1)*mutual_info(static_data, moving_resampled, 64)

        return neg_MI

    def MI_cost_rotation(rotations):
        ## cost function for rotations using MI
        #create affine from new params
        rot_mat = make_rot_mat(rotations)
        shift_affine = nib.affines.from_matvec(rot_mat, np.zeros(3))

        updated_moving_affine = moving_affine_translated.dot(shift_affine)

        #resample with new affine
        moving_resampled = resample(static_data, moving_data, static_affine, updated_moving_affine)

        #get negative mutual information (static & new moving)
        neg_MI = (-1)*mutual_info(static_data, moving_resampled, 32)

        return neg_MI

    def make_rot_mat(rotations):
        ##make (3,3) rotation matrix from radian rotation parameters
        r_x,r_y,r_z = rotations
        rot_mat = z_rotmat(r_z).dot(y_rotmat(r_y)).dot(x_rotmat(r_x))
        return rot_mat

    # get best translations
    if partial in [0,1]:
        best_translations = fmin_powell(MI_cost_translation, [0,0,0], maxiter = iter)
    else:
        best_translations = [0,0,0]
    best_translations_affine = nib.affines.from_matvec(np.eye(3), best_translations)

    # update moving affine to use best translation
    moving_affine_translated = moving_affine.dot(best_translations_affine)

    #get best rotations
    if partial in [0,2]:
        best_rotations = fmin_powell(MI_cost_rotation, [0,0,0], maxiter = iter)
    else:
        best_rotations = [0,0,0]

    # combine best translations and rotations
    best_rotations_mat = make_rot_mat(best_rotations)
    updated_moving_affine = nib.affines.from_matvec(best_rotations_mat, best_translations)

    return updated_moving_affine


def mutual_info(static_data, moving_data, nbins):
    """ get mutual information (MI) between 2 arrays
    Parameters
    ----------
    static_data : array shape (I, J, ...)
        array of image 1

    moving_data : array shape (I, J, ...)
        array of image 2

    nbins : int
        number bins for MI

    Returns
    -------
    MI : float
        mutual information value

    """

    hist_2d, x_edges, y_edges = np.histogram2d(static_data.ravel(), moving_data.ravel(), bins=nbins) #get bin counts

    hist_2d_p = hist_2d/float(hist_2d.sum()) #p(x,y)
    nzs = hist_2d_p > 0 #idx for cells>0

    px = hist_2d_p.sum(axis=1) #marginal over y
    py = hist_2d_p.sum(axis=0) #marginal over x

    px_py = px[:,None] * py[None,:] #p(x)*p(y)
    MI = (hist_2d_p[nzs] * np.log(hist_2d_p[nzs]/px_py[nzs])).sum()

    return MI
