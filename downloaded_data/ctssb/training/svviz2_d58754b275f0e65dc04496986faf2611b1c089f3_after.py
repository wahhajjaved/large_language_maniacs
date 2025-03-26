import logging
import numpy

from svviz2.io import export
from svviz2.app import genomesource
from svviz2.visualize import dotplots

from genomeview import Document, ViewRow, GenomeView
from genomeview.track import TrackLabel
from genomeview.axis import Axis, get_ticks
from genomeview.intervaltrack import IntervalTrack, Interval
from genomeview.bamtrack import SingleEndBAMTrack, PairedEndBAMTrack

logger = logging.getLogger(__name__)



def get_bounds(datahub, allele, part):
    start = len(part.segments[0])
    end = sum(len(segment) for segment in part.segments[:-1])

    for sample in datahub.samples.values():
        for read in sample.outbam(allele, "r").fetch(part.id):
            start = min(start, read.reference_start)
            end = max(end, read.reference_end)

    if start >= end:
        return 0, len(part)

    width = end - start
    start -= width * 0.1
    end += width * 0.1

    start = max(start, 0)
    end = min(end, len(part))
    
    return int(start), int(end)

def get_bounds_zoomed(part, context_bases):
    start = len(part.segments[0]) - context_bases
    end = len(part) - (len(part.segments[-1])-context_bases)

    start = max(0, start)
    
    return start, end



# TODO: this is svviz2.visualize.visualize.visualize -- awkward!
def visualize(datahub):#, temp_storage):
    if datahub.args.also_plot_context:
        logger.info("Now plotting zoomed-in")
        _visualize(datahub, context=datahub.args.also_plot_context)

    if datahub.args.only_plot_context:
        _visualize(datahub, context=datahub.args.only_plot_context)
    else:
        _visualize(datahub)


def _visualize(datahub, context=None):
    doc = Document(1500)
    doc.elements.append(TrackLabel(str(datahub.variant)))

    for allele in ["alt", "ref"]:
        row = ViewRow(allele)

        for part in datahub.variant.chrom_parts(allele):
            source = genomesource.GenomeSource({part.id:part.get_seq()})

            if context is None:
                start, end = get_bounds(datahub, allele, part)
            else:
                start, end = get_bounds_zoomed(part, context)

            genome_view = GenomeView(part.id, start, end, "+", source, name=part.id)

            for sample_name, sample in datahub.samples.items():
                bam_path = sample.outbam_paths[allele].replace(".bam", ".sorted.bam") ## XXX todo: refactor
                class_ = SVSingleEndBAMTrack if sample.single_ended else SVPairedEndBAMTrack

                bam_track = class_(bam_path, part.segments, name=sample_name)
                bam_track.color_fn = color_by_strand_with_mapq
                bam_track.draw_read_labels = False

                genome_view.add_track(bam_track)

            axis = ChromSegmentAxis(part.segments, part.id)
            genome_view.add_track(axis)
            trf_track = get_trf_track(datahub, allele, part)
            if trf_track:
                genome_view.add_track(trf_track)

            row.add_view(genome_view)

        if allele == "alt": track_label = "Alternate Allele"
        elif allele == "ref": track_label = "Reference Allele"
        
        doc.elements.append(TrackLabel(track_label))
        doc.elements.append(row)


    export.export(doc, datahub, context)

def get_trf_track(datahub, allele, part):
    repeats = dotplots.detect_simple_repeats(part.get_seq())
    if repeats is None:
        return None

    intervals = []

    for i, (start, end, repeat) in enumerate(repeats):
        # print("--", start, end, repeat)
        label = label="({}){:.1f}".format(repeat, (end-start)/len(repeat))
        if len(label) > 20:
            label = "long_repeat_{}".format(i)
        intervals.append(
            Interval(i, part.id, start, end, "+", label))

    track = IntervalTrack(intervals, "repeats-{}".format(part.id))
    track.color_fn = lambda x: "gray"

    return track

    
#### TODO: this should move elsewhere!!

def color_by_strand_with_mapq(interval):
    color = numpy.array([232,158,157])
    if interval.strand == "-":
        color = numpy.array([140,143,206])

    brightness = 0.2 + (interval.read.mapq/40.0*0.8)

    if brightness != 1.0:
        color = color * brightness + numpy.array([255., 255., 255.])*(1-brightness)
    
    color = "rgb({},{},{})".format(*map(int, color))
    return color

def render_breakpoints(renderer, bam_track):
    if len(bam_track.intervals_to_rows) > 0:            
        cur_coord = 0
        for segment in bam_track.segments[:-1]:
            cur_coord += len(segment)
            cur_pos = bam_track.scale.topixels(cur_coord)
            yield from renderer.line(cur_pos, 0, cur_pos, bam_track.height)
    else:
        yield from renderer.text(bam_track.scale.pixel_width/2, 14, "No reads found", fill="gray", size=18)


class SVSingleEndBAMTrack(SingleEndBAMTrack):
    def __init__(self, bam_path, segments, name=None):
        super().__init__(bam_path, name=name)
        self.segments = segments
        self.min_indel_size = 5
        self.min_insertion_label_size = 10
        
        self.draw_read_labels = False
        
    def render(self, renderer):
        yield from render_breakpoints(renderer, self)
        yield from super().render(renderer)
        
    def layout(self, scale):
        super().layout(scale)
        self.height = max(25, self.height)

class SVPairedEndBAMTrack(PairedEndBAMTrack):
    def __init__(self, bam_path, segments, name=None):
        super().__init__(bam_path, name=name)
        self.segments = segments
        self.draw_read_labels = False
        
    def render(self, renderer):
        yield from render_breakpoints(renderer, self)
        yield from super().render(renderer)
        
    def layout(self, scale):
        super().layout(scale)
        self.height = max(25, self.height)
            
class ChromSegmentAxis(Axis):
    def __init__(self, chrom_segments, name=None):
        super().__init__(name)
        self.chrom_segments = chrom_segments
        self.height

    def render(self, renderer):
        start, end = self.scale.start, self.scale.end
        
        cur_start = 0
        arrow_size = 20
        arrow_spacing = 30
        y = arrow_size/2
        bar_height = 5

        ticks = get_ticks(start, end, max(1,self.scale.pixel_width/120))
        for i, (tick, label) in enumerate(ticks):
            x = self.scale.topixels(tick)
            if x < 0 or x > self.scale.pixel_width: continue

            yield from renderer.line(x, y, x, 20)

            anchor = "middle"
            if x < 50 and i == 0:
                anchor = "start"
                x = min(x, 5)
            elif x > self.scale.pixel_width-50 and i == len(ticks)-1:
                anchor = "end"
                x = max(x, self.scale.pixel_width-5)

            yield from renderer.text(x, y+30, label, anchor=anchor, size=16)


        for segment in self.chrom_segments:
            cur_end = cur_start + len(segment)
            left = self.scale.topixels(cur_start)
            width = self.scale.topixels(cur_end) - left
            yield from renderer.rect(left, y-bar_height/2, width, bar_height,
                                     fill=segment.color(), stroke="none")

            direction = "right" if segment.strand=="+" else "left"
            x = 0
            count = 0
            while x < (width-arrow_size) or count == 0:
                yield from renderer.arrow(left+x+arrow_size, y, direction,
                    color=segment.color(), scale=arrow_size/10)
                x += arrow_size+arrow_spacing
                count += 1

            cur_start += len(segment)

