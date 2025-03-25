import cv2
import numpy as np
import pytest
from mmedit.datasets.pipelines import (CompositeFg, GenerateSoftSeg,
                                       GenerateTrimap, MergeFgAndBg, PerturbBg)


def check_keys_contain(result_keys, target_keys):
    """Check if all elements in target_keys is in result_keys."""
    return set(target_keys).issubset(set(result_keys))


def generate_ref_trimap(alpha, kernel_size, iterations, random):
    """Check if a trimap's value is correct."""
    if isinstance(kernel_size, int):
        kernel_size = kernel_size, kernel_size + 1
    if isinstance(iterations, int):
        iterations = iterations, iterations + 1

    if random:
        min_kernel, max_kernel = kernel_size
        kernel_num = max_kernel - min_kernel
        erode_ksize = min_kernel + np.random.randint(kernel_num)
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                 (erode_ksize, erode_ksize))
        dilate_ksize = min_kernel + np.random.randint(kernel_num)
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                  (dilate_ksize, dilate_ksize))

        min_iteration, max_iteration = iterations
        erode_iter = np.random.randint(min_iteration, max_iteration)
        dilate_iter = np.random.randint(min_iteration, max_iteration)
    else:
        erode_ksize, dilate_ksize = kernel_size
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                 (erode_ksize, erode_ksize))
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                  (dilate_ksize, dilate_ksize))
        erode_iter, dilate_iter = iterations

    h, w = alpha.shape

    # erode
    erode_kh = erode_kw = erode_ksize
    eroded = np.zeros_like(alpha)
    src = alpha
    pad = ((erode_kh // 2, (erode_kh - 1) // 2), (erode_kw // 2,
                                                  (erode_kw - 1) // 2))
    for _ in range(erode_iter):
        src = np.pad(src, pad, 'constant', constant_values=np.max(src))
        for i in range(h):
            for j in range(w):
                target = src[i:i + erode_kh, j:j + erode_kw]
                eroded[i, j] = np.min(
                    (target * erode_kernel)[erode_kernel == 1])
        src = eroded

    # dilate
    dilate_kh = dilate_kw = dilate_ksize
    dilated = np.zeros_like(alpha)
    src = alpha
    pad = ((dilate_kh // 2, (dilate_kh - 1) // 2), (dilate_kw // 2,
                                                    (dilate_kw - 1) // 2))
    for _ in range(dilate_iter):
        src = np.pad(src, pad, constant_values=np.min(src))
        for i in range(h):
            for j in range(w):
                target = src[i:i + dilate_kh, j:j + dilate_kw]
                dilated[i, j] = np.max(
                    (target * dilate_kernel)[dilate_kernel == 1])
        src = dilated

    ref_trimap = np.zeros_like(alpha)
    ref_trimap.fill(128)
    ref_trimap[eroded >= 255] = 255
    ref_trimap[dilated <= 0] = 0
    return ref_trimap


def test_merge_fg_and_bg():
    target_keys = ['fg', 'bg', 'alpha', 'merged']

    fg = np.random.randn(32, 32, 3)
    bg = np.random.randn(32, 32, 3)
    alpha = np.random.randn(32, 32)
    results = dict(fg=fg, bg=bg, alpha=alpha)
    merge_fg_and_bg = MergeFgAndBg()
    merge_fg_and_bg_results = merge_fg_and_bg(results)

    assert check_keys_contain(merge_fg_and_bg_results.keys(), target_keys)
    assert merge_fg_and_bg_results['merged'].shape == fg.shape


def test_generate_trimap():
    with pytest.raises(ValueError):
        # kernel_size must be an int or a tuple of 2 int
        GenerateTrimap(1.5)

    with pytest.raises(ValueError):
        # kernel_size must be an int or a tuple of 2 int
        GenerateTrimap((3, 3, 3))

    with pytest.raises(ValueError):
        # iterations must be an int or a tuple of 2 int
        GenerateTrimap(3, iterations=1.5)

    with pytest.raises(ValueError):
        # iterations must be an int or a tuple of 2 int
        GenerateTrimap(3, iterations=(3, 3, 3))

    target_keys = ['alpha', 'trimap']

    # check random mode
    kernel_size = (3, 5)
    iterations = (3, 5)
    random = True
    alpha = np.random.randn(32, 32)
    results = dict(alpha=alpha)
    generate_trimap = GenerateTrimap(kernel_size, iterations, random)
    np.random.seed(123)
    generate_trimap_results = generate_trimap(results)
    trimap = generate_trimap_results['trimap']

    assert check_keys_contain(generate_trimap_results.keys(), target_keys)
    assert trimap.shape == alpha.shape
    np.random.seed(123)
    ref_trimap = generate_ref_trimap(alpha, kernel_size, iterations, random)
    assert (trimap == ref_trimap).all()

    # check non-random mode
    kernel_size = (3, 5)
    iterations = (5, 3)
    random = False
    generate_trimap = GenerateTrimap(kernel_size, iterations, random)
    generate_trimap_results = generate_trimap(results)
    trimap = generate_trimap_results['trimap']

    assert check_keys_contain(generate_trimap_results.keys(), target_keys)
    assert trimap.shape == alpha.shape
    ref_trimap = generate_ref_trimap(alpha, kernel_size, iterations, random)
    assert (trimap == ref_trimap).all()

    # check repr string
    kernel_size = 1
    iterations = 1
    generate_trimap = GenerateTrimap(kernel_size, iterations)
    kernels = [
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                  (kernel_size, kernel_size))
    ]
    assert repr(generate_trimap) == (
        generate_trimap.__class__.__name__ +
        f'(kernels={kernels}, iterations={(iterations, iterations + 1)}, '
        f'random=True)')


def test_composite_fg():
    target_keys = ['alpha', 'fg', 'bg', 'img_shape']

    np.random.seed(0)
    fg = np.random.rand(32, 32, 3).astype(np.float32)
    bg = np.random.rand(32, 32, 3).astype(np.float32)
    alpha = np.random.rand(32, 32).astype(np.float32)
    results = dict(alpha=alpha, fg=fg, bg=bg, img_shape=(32, 32))
    composite_fg = CompositeFg('tests/data/fg', 'tests/data/alpha', 'jpg',
                               'jpg')
    composite_fg_results = composite_fg(results)
    assert check_keys_contain(composite_fg_results.keys(), target_keys)
    assert composite_fg_results['fg'].shape == (32, 32, 3)

    fg = np.random.rand(32, 32, 3).astype(np.float32)
    bg = np.random.rand(32, 32, 3).astype(np.float32)
    alpha = np.random.rand(32, 32).astype(np.float32)
    results = dict(alpha=alpha, fg=fg, bg=bg, img_shape=(32, 32))
    composite_fg = CompositeFg(
        'tests/data/fg',
        'tests/data/alpha',
        fg_ext='jpg',
        alpha_ext='jpg',
        interpolation='bilinear')
    composite_fg_results = composite_fg(results)
    assert check_keys_contain(composite_fg_results.keys(), target_keys)
    assert composite_fg_results['fg'].shape == (32, 32, 3)

    assert repr(composite_fg) == composite_fg.__class__.__name__ + (
        "(fg_dir='tests/data/fg', alpha_dir='tests/data/alpha', "
        "fg_ext='jpg', alpha_ext='jpg', interpolation='bilinear')")


def test_perturb_bg():
    with pytest.raises(ValueError):
        # gammma_ratio must be a float between [0, 1]
        PerturbBg(-0.5)

    with pytest.raises(ValueError):
        # gammma_ratio must be a float between [0, 1]
        PerturbBg(1.1)

    target_keys = ['bg', 'noisy_bg']
    # set a random seed to make sure the test goes through every branch
    np.random.seed(123)

    img_shape = (32, 32, 3)
    results = dict(bg=np.random.randint(0, 255, img_shape))
    perturb_bg = PerturbBg(0.6)
    perturb_bg_results = perturb_bg(results)
    assert check_keys_contain(perturb_bg_results.keys(), target_keys)
    assert perturb_bg_results['noisy_bg'].shape == img_shape

    img_shape = (32, 32, 3)
    results = dict(bg=np.random.randint(0, 255, img_shape))
    perturb_bg = PerturbBg(0.6)
    perturb_bg_results = perturb_bg(results)
    assert check_keys_contain(perturb_bg_results.keys(), target_keys)
    assert perturb_bg_results['noisy_bg'].shape == img_shape

    repr_str = perturb_bg.__class__.__name__ + '(gamma_ratio=0.6)'
    assert repr(perturb_bg) == repr_str


def test_generate_soft_seg():
    with pytest.raises(TypeError):
        # fg_thr must be a float
        GenerateSoftSeg(fg_thr=[0.2])
    with pytest.raises(TypeError):
        # border_width must be an int
        GenerateSoftSeg(border_width=25.)
    with pytest.raises(TypeError):
        # erode_ksize must be an int
        GenerateSoftSeg(erode_ksize=5.)
    with pytest.raises(TypeError):
        # dilate_ksize must be an int
        GenerateSoftSeg(dilate_ksize=5.)
    with pytest.raises(TypeError):
        # erode_iter_range must be a tuple of 2 int
        GenerateSoftSeg(erode_iter_range=(3, 5, 7))
    with pytest.raises(TypeError):
        # dilate_iter_range must be a tuple of 2 int
        GenerateSoftSeg(dilate_iter_range=(3, 5, 7))
    with pytest.raises(TypeError):
        # blur_ksizes must be a list of tuple
        GenerateSoftSeg(blur_ksizes=[21, 21])

    target_keys = ['seg', 'soft_seg', 'img_shape']

    seg = np.random.randint(0, 255, (512, 512))
    results = dict(seg=seg, img_shape=seg.shape)

    generate_soft_seg = GenerateSoftSeg(
        erode_ksize=3,
        dilate_ksize=3,
        erode_iter_range=(1, 2),
        dilate_iter_range=(1, 2),
        blur_ksizes=[(11, 11)])
    generate_soft_seg_results = generate_soft_seg(results)
    assert check_keys_contain(generate_soft_seg_results.keys(), target_keys)
    assert generate_soft_seg_results['soft_seg'].shape == seg.shape

    repr_str = generate_soft_seg.__class__.__name__ + (
        '(fg_thr=0.2, border_width=25, erode_ksize=3, dilate_ksize=3, '
        'erode_iter_range=(1, 2), dilate_iter_range=(1, 2), '
        'blur_ksizes=[(11, 11)])')
    assert repr(generate_soft_seg) == repr_str
