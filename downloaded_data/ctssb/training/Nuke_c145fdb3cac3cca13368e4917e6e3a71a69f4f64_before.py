# -*- coding=UTF-8 -*-
"""Do motion distort for rotopaint strokes.  """

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import nuke
from nuke.rotopaint import CVec3
from six.moves import range

from nuketools import undoable_func, utf8
from rotopaint_tools import (LIFETIME_TYPE_ALL, RelativePointProxy, iter_layer,
                             iter_shape_point)
from wlf.progress import progress
from wlf.progress.handlers.nuke import NukeProgressHandler
from wlf_tools.progress import CustomMessageProgressHandler


def _is_point_single_key(point):
    return all(
        len(p.getControlPointKeyTimes()) == 1
        for p in iter_shape_point(point)
    )


def _is_shape_single_key(shape):
    return all(_is_point_single_key(p) for p in shape)


def _motion_distort_rotopaint_anim_point_frame(
        motion, point, frame, direction):
    base_frame = frame-direction
    motion_frame = base_frame
    if direction < 0:
        motion_frame -= 1
    base_pos = point.getPosition(base_frame)
    offset = CVec3(
        motion.sample(utf8("forward.u"),
                      base_pos.x,
                      base_pos.y,
                      frame=motion_frame),
        motion.sample(utf8("forward.v"),
                      base_pos.x,
                      base_pos.y,
                      frame=motion_frame),
    )
    computed_pos = base_pos + offset*direction

    def _job():
        point.addPositionKey(frame, computed_pos)

    return _job


def _motion_distort_rotopaint_shape_point_frame(
        motion, point, frame, direction):
    # we should change center after sample finished.
    deferred_jobs = []
    for i in iter_shape_point(point):
        job = _motion_distort_rotopaint_anim_point_frame(
            motion,
            i,
            frame,
            direction,
        )
        deferred_jobs.append(job)

    for i in deferred_jobs:
        i()


def _remove_shape_point_position_key(point, frame):
    for i in iter_shape_point(point):
        i.removePositionKey(frame)


def _motion_distort_rotopaint_shape_point(
        motion, point, base_frame, frame_gte, frame_lte, interval):
    # base
    _motion_distort_rotopaint_shape_point_frame(motion, point, base_frame, 0)
    # backward
    for i in range(base_frame-1, frame_gte-1, -1):
        _motion_distort_rotopaint_shape_point_frame(
            motion, point, i, -1)
    # forward
    for i in range(base_frame+1, frame_lte+1):
        _motion_distort_rotopaint_shape_point_frame(
            motion, point, i, 1)
    # interval
    for i in range(frame_gte, frame_lte + 1):
        if (i - base_frame) % interval != 0:
            _remove_shape_point_position_key(point, i)


def _motion_distort_rotopaint_shape(
        motion, shape, base_frame, frame_gte, frame_lte, interval):
    for i in shape:
        _motion_distort_rotopaint_shape_point(
            motion, i, base_frame, frame_gte, frame_lte, interval)


GENERATED_SHAPE_SUFFIX = ".MotionDistort"


def _iter_matched_shape(layer):
    for i in iter_layer(layer):
        if not isinstance(i, nuke.rotopaint.Shape):
            continue
        attrs = i.getAttributes()
        visible_curve = attrs.getCurve(attrs.kVisibleAttribute)
        if (not visible_curve.constantValue
                or visible_curve.getNumberOfKeys() > 0):
            continue
        lifetime_type = attrs.getCurve(
            attrs.kLifeTimeTypeAttribute).constantValue
        if lifetime_type != LIFETIME_TYPE_ALL:
            continue
        if not (
                i.name.endswith(GENERATED_SHAPE_SUFFIX)
                or _is_shape_single_key(i)
        ):
            continue
        yield i


@undoable_func("RotoPaint 运动扭曲")
def create_rotopaint_motion_distort(
        rotopaint, base_frame, frame_gte, frame_lte, interval):
    """Create motion distort shape for condition matched shape.

    Args:
        rotopaint (nuke.nodes.RotoPaint): RotoPaint node that contains
            motion data and shape.
        base_frame (int): Base frame to motion from.
        frame_gte (int): Frame range start.
        frame_lte (int): Frame range end.
        interval (int): Keep keyframe every n frame
            for generated shape, remove others.
    """
    assert isinstance(rotopaint, nuke.Node)
    assert rotopaint.Class() == "RotoPaint", (
        "should be rotopaint, got {}".format(rotopaint.Class()))
    layer = rotopaint["curves"].rootLayer
    existed_shape = {i.name: i for i in iter_layer(layer)}
    for i in progress(
            list(_iter_matched_shape(layer)),
            rotopaint.name(),
            handler=CustomMessageProgressHandler(
                lambda i: i.name,
            ),
    ):
        name = i.name
        is_generated = name.endswith(GENERATED_SHAPE_SUFFIX)
        if not is_generated:
            name += utf8(GENERATED_SHAPE_SUFFIX)
        v = existed_shape.get(name) or i.clone()
        v.name = name

        if not is_generated:
            attrs = i.getAttributes()
            attrs.getCurve(attrs.kVisibleAttribute).constantValue = False
            i.locked = True

        _motion_distort_rotopaint_shape(
            rotopaint,
            v,
            base_frame,
            frame_gte,
            frame_lte,
            interval,
        )


def show_dialog():
    """Show GUI dialog for `create_rotopaint_motion_distort`."""

    nodes = nuke.selectedNodes("RotoPaint")

    if not nodes:
        nuke.message(utf8("请选中RotoPaint节点"))
        return

    # Node.sample need a transformed position when using proxy
    nuke.Root()["proxy"].setValue(False)

    def _tr(key):
        return utf8({
            'start': '起始帧',
            'end': '结束帧',
            'base': '基准帧',
            "interval": "间隔",
        }.get(key, key))

    panel = nuke.Panel("创建 RotoPaint 运动扭曲".encode("utf8"))
    panel.addExpressionInput(_tr('base'), nuke.frame())
    panel.addExpressionInput(_tr('start'), nuke.numvalue("root.first_frame"))
    panel.addExpressionInput(_tr('end'), nuke.numvalue("root.last_frame"))
    panel.addExpressionInput(_tr('interval'), 1)
    if not panel.show():
        return
    base = int(panel.value(_tr('base')))
    start = int(panel.value(_tr('start')))
    end = int(panel.value(_tr('end')))
    interval = int(panel.value(_tr('interval')))
    for n in progress(
            nodes, "RotoPaint 运动扭曲",
            handler=CustomMessageProgressHandler(
                lambda i: i.name()
            ),
    ):
        channels = n.channels()
        if not ("forward.u" in channels and "forward.v" in channels):
            nuke.message(
                utf8("节点 {} 缺少 forward.u 和 forward.v 通道，将跳过")
                .format(n.getName())
            )
            continue
        create_rotopaint_motion_distort(n, base, start, end, interval)
