import collections
import math

from intervaltree import Interval, IntervalTree
from matplotlib.patches import Rectangle

from coolbox.utilities import (change_chrom_names, get_logger,
                               opener, rgb2hex, to_string)
from .base import Coverage

log = get_logger(__name__)

STYLE_TRIANGULAR = 'triangular'
STYLE_MATRIX = 'matrix'
STYLE_WINDOW = 'window'

DEPTH_FULL = 'full'


class HiCPeaks(Coverage):
    """
    Hi-C Peaks(Loops) Coverge is a special kind of Coverage.
    Used to show the peaks on the Hi-C interaction map.

    Parameters
    ----------
    file_ : str
        Path to the loop file, loop file is a tab splited text file, fields:
        chr1, x1, x2, chr2, y1, y2, [color], ... (other optional fields)

    color : str, optional
        Peak color, use 'bed_rgb' for specify color in file,
        default 'bed_rgb'.

    alpha : float, optional
        Peak alpha value, default 0.6.

    line_width : float, optional
        Peak border line width, default 1.0

    line_style : str, optional
        Border line style, default 'solid'

    fill : bool, optional
        Fill center or not, default False.

    fill_color : str, optional
        Fill color, use 'bed_rgb' for specify color in file,
        default 'bed_rgb'.

    side : {'upper', 'lower', 'both'}
        Plot peak in which side of the matrix.
        NOTE: This parameters is useful only if the Cool track in matrix format.
    """

    DEFAULT_COLOR = "#2255ff"

    def __init__(self, file_, **kwargs):
        properties_dict = {
            "file": file_,
            "color": "bed_rgb",
            "alpha": 0.6,
            "line_width": 5,
            "line_style": "solid",
            "fill": False,
            "fill_color": "bed_rgb",
            "side": "both",
        }
        properties_dict.update(kwargs)
        super().__init__(properties_dict)
        self.LoopInverval = collections.namedtuple("LoopInterval",
                                                   ("chr1", "x1", "x2", "chr2", "y1", "y2", "color"))
        self.interval_tree = self.__process_loop_file()

    def plot(self, ax, chrom_region, start_region, end_region):

        if chrom_region not in self.interval_tree:
            chrom_region = change_chrom_names(chrom_region)

        if hasattr(self.track, 'fetch_region'):
            start_fetch = self.track.fetch_region.start
            end_fetch = self.track.fetch_region.end
        else:
            start_fetch, end_fetch = start_region, end_region

        for intval in sorted(self.interval_tree[chrom_region][start_fetch:end_fetch]):
            loop = intval.data

            if (self.properties['color'] == 'rgb') or (self.properties['color'] == 'bed_rgb'):
                color = loop.color
            else:
                color = self.properties['color']

            if (self.properties['fill_color']) == 'rgb' or (self.properties['fill_color'] == 'bed_rgb'):
                fill_color = loop.color
            else:
                fill_color = self.properties['fill_color']

            fill = True if self.properties['fill'] == 'yes' else False

            self.properties['style'] = self.track.properties['style']
            self.properties['depth_ratio'] = self.track.properties['depth_ratio']

            if self.properties['style'] == STYLE_TRIANGULAR or self.properties['style'] == STYLE_WINDOW:

                depth_ratio = self.properties['depth_ratio'] if self.properties['depth_ratio'] != DEPTH_FULL else 1

                region_length = (end_region - start_region)
                depth_full = region_length * 0.5
                depth_limit = depth_full * depth_ratio

                x, y, (w, h) = self.__get_position_and_size(loop.x1, loop.x2, loop.y1, loop.y2,
                                                            style=self.properties['style'])

                if y >= depth_limit:
                    continue

                rec = Rectangle((x, y), w, h, angle=45,
                                fill=fill,
                                alpha=self.properties['alpha'],
                                facecolor=fill_color,
                                edgecolor=color,
                                linewidth=self.properties['line_width'],
                                linestyle=self.properties['line_style'])
                ax.add_patch(rec)

            elif self.properties['style'] == STYLE_MATRIX:

                if self.properties['side'] == 'upper' or self.properties['side'] == 'both':
                    # plot upper rectangle
                    x, y, (w, h) = self.__get_position_and_size(loop.x1, loop.x2, loop.y1, loop.y2,
                                                                style=STYLE_MATRIX, side="upper")
                    rec = Rectangle((x, y), w, h,
                                    fill=fill,
                                    alpha=self.properties['alpha'],
                                    facecolor=fill_color,
                                    edgecolor=color,
                                    linewidth=self.properties['line_width'],
                                    linestyle=self.properties['line_style'])
                    ax.add_patch(rec)

                if self.properties['side'] == 'lower' or self.properties['side'] == 'both':
                    # plot lower rectangle
                    x, y, (w, h) = self.__get_position_and_size(loop.x1, loop.x2, loop.y1, loop.y2,
                                                                style=STYLE_MATRIX, side="lower")
                    rec = Rectangle((x, y), w, h,
                                    fill=fill,
                                    alpha=self.properties['alpha'],
                                    facecolor=fill_color,
                                    edgecolor=color,
                                    linewidth=self.properties['line_width'],
                                    linestyle=self.properties['line_style'])
                    ax.add_patch(rec)

    def __get_position_and_size(self, start1, end1, start2, end2,
                                style=STYLE_TRIANGULAR, side="upper"):
        """
        Calculate the position and size of the box from loop's start and end postion.
        """

        if style == STYLE_TRIANGULAR or style == STYLE_WINDOW:
            m1 = (start1 + end1) / 2
            m2 = (start2 + end2) / 2
            x = (m1 + m2) / 2
            y = x - m1
            w = ((end2 - start2) / 2) / math.cos(math.pi / 4)
            h = ((end1 - start1) / 2) / math.cos(math.pi / 4)
        elif style == STYLE_MATRIX:
            if side == "upper":
                x = (start2 + end2) / 2
                y = (start1 + end1) / 2
                w = end2 - start2
                h = end1 - start1
            else:
                x = (start1 + end1) / 2
                y = (start2 + end2) / 2
                w = end1 - start1
                h = end2 - start2
        return x, y, (w, h)

    def __process_loop_file(self):
        interval_tree = {}

        with opener(self.properties['file']) as f:
            for idx, line in enumerate(f):
                line = to_string(line)
                # skip header line
                if idx == 0 and self.__is_header(line):
                    continue

                fields = line.split()
                chr1, x1, x2, chr2, y1, y2, *other = fields
                x1, x2, y1, y2 = list(map(int, [x1, x2, y1, y2]))

                # skip inter-chromosome interaction
                if chr1 != chr2:
                    continue
                chromosome = chr1

                if not chromosome.startswith("chr"):
                    chromosome = change_chrom_names(chromosome)
                if chromosome not in interval_tree:
                    interval_tree[chromosome] = IntervalTree()

                if len(other) == 0:
                    color = self.DEFAULT_COLOR
                else:
                    rgb = other[0].split(",")
                    rgb = list(map(int, rgb))
                    color = rgb2hex(*rgb)

                loop = self.LoopInverval(chr1, x1, x2, chr2, y1, y2, color)
                interval_tree[chromosome].add(Interval(x1, y2, loop))

        return interval_tree

    def __is_header(self, line):
        fields = line.split()
        for idx in [1, 2, 4, 5]:
            if not fields[idx].isdigit():
                return True
        return False
