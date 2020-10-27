import subprocess as subp

import numpy as np
from dna_features_viewer import GraphicFeature, GraphicRecord

from coolbox.plots.track.base import TrackPlot
from coolbox.plots.track.bigwig import CoveragePlot
from coolbox.utilities import (
    get_logger, GenomeRange
)

log = get_logger(__name__)


def coverage_by_samtools(bam_path, region, bins):
    cmd = ["samtools", "coverage", bam_path, "-r", region, "-w", str(bins)]
    p = subp.Popen(cmd, stdout=subp.PIPE)
    lines = []
    for line in p.stdout:
        line = line.decode('utf-8')
        lines.append(line)
    covs = parse_samtools_cov(lines)
    return np.array(covs)


def parse_samtools_cov(lines):
    covs = {}
    for line in lines[1:-1]:
        left, mid, _ = line.split("│")
        percent = float(left.strip("> %"))
        for i, c in enumerate(mid):
            covs.setdefault(i, 0)
            if c != ' ' and covs[i] == 0:
                covs[i] = percent
    covs = [covs[i] for i in sorted(covs.keys())]
    return covs


class PlotBAM(TrackPlot, CoveragePlot):

    def __init__(self, *args, **kwargs):
        TrackPlot.__init__(self, *args, **kwargs)

    def plot(self, ax, chrom_region, start_region, end_region):
        gr = GenomeRange(chrom_region, start_region, end_region)
        ptype = self.properties.get("plot_type", "alignment")
        self.ax = ax
        if ptype == "alignment":
            self.plot_align(ax, gr)
        else:
            self.plot_coverage(ax, gr)

    def plot_align(self, ax, genome_range):
        gr = genome_range
        df = self.fetch_intervals(gr)
        df_ = df[np.bitwise_and(df['flag'], 0b100) == 0]
        len_thresh = self.properties.get("length_ratio_thresh", 0.005)
        df_ = df_[df_['seq'].str.len() > (gr.length * len_thresh)]
        if df_.shape[0] <= 0:
            return
        rev_flag = np.bitwise_and(df['flag'], 0b10000) != 0
        features = []
        for idx, row in df_.iterrows():
            start = row['pos'] - gr.start
            end = row['pos'] + len(row['seq']) - gr.start
            strand = -1 if rev_flag.iloc[idx] else 1
            gf = GraphicFeature(
                start=start,
                end=end,
                strand=strand,
                color=self.properties['color'],
            )
            features.append(gf)
        record = GraphicRecord(sequence_length=gr.length, features=features)
        record.plot(
            ax=ax,
            with_ruler=False,
            draw_line=False
        )

    def plot_coverage(self, ax, genome_range):
        gr = genome_range
        bins = self.properties.get("bins", 40)
        scores_per_bin = coverage_by_samtools(self.indexed_bam, str(gr), bins)
        super().plot_coverage(ax, genome_range, scores_per_bin)
        self.plot_label()