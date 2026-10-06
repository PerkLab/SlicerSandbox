"""Examples of interactive Matplotlib figures shown in the view layout.

Both examples use the MRHead sample volume. Run them from the module panel or from the
Python console::

    import InteractiveMatplotlibLib.examples as examples
    examples.showSliceHistogram()
    examples.showSegmentStatistics()  # also needs seaborn and pandas
"""

import numpy as np
import vtk
from vtk.util import numpy_support

import slicer
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

import InteractiveMatplotlibLib.view as view


class SliceHistogramPlot:
    """Interactive Matplotlib histogram of the slice currently shown in a slice view.

    Scrolling the slice view updates the histogram of the slice that is displayed, and
    dragging a range over the histogram applies it as the window/level of the volume.
    """

    def __init__(self, volumeNode, sliceViewName="Red"):
        self.volumeNode = volumeNode
        self.sliceLogic = slicer.app.layoutManager().sliceWidget(sliceViewName).sliceLogic()
        self.sliceNode = self.sliceLogic.GetSliceNode()

        self.figure = Figure(tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        # Show the figure next to the slice views. It now has the canvas that the
        # span selector connects to.
        self.canvas = view.showFigure(self.figure)

        # Drag over the histogram to apply that intensity range as window/level.
        self.spanSelector = SpanSelector(
            self.axes, self.onIntensityRangeSelected, "horizontal",
            useblit=True, props=dict(alpha=0.3, facecolor="tab:orange"),
            interactive=True, drag_from_anywhere=True)

        self.sliceObserver = self.sliceNode.AddObserver(
            vtk.vtkCommand.ModifiedEvent, self.onSliceModified)
        self.update()

    def cleanup(self):
        """Stop following the slice view and remove the plot from the layout."""
        if self.sliceObserver is not None:
            self.sliceNode.RemoveObserver(self.sliceObserver)
            self.sliceObserver = None
        widget = view.viewWidget()
        if widget is not None and widget.figure() is self.figure:
            widget.setFigure(None)

    def currentSliceArray(self):
        """Voxels of the reslice actually displayed, for any slice orientation."""
        reslice = self.sliceLogic.GetBackgroundLayer().GetReslice()
        reslice.Update()
        scalars = reslice.GetOutput().GetPointData().GetScalars()
        if scalars is None:
            return None
        return numpy_support.vtk_to_numpy(scalars)

    def onSliceModified(self, caller=None, event=None):
        self.update()

    def onIntensityRangeSelected(self, minIntensity, maxIntensity):
        if maxIntensity <= minIntensity:
            return
        displayNode = self.volumeNode.GetDisplayNode()
        displayNode.AutoWindowLevelOff()
        displayNode.SetWindowLevelMinMax(minIntensity, maxIntensity)

    def update(self):
        voxels = self.currentSliceArray()
        self.axes.clear()
        if voxels is not None and voxels.size:
            # Ignore the zero-valued background that reslicing introduces.
            voxels = voxels[voxels > 0]
        if voxels is not None and voxels.size:
            self.axes.hist(voxels, bins=80, color="tab:blue")
        self.axes.set_xlabel("Intensity")
        self.axes.set_ylabel("Voxel count")
        self.axes.set_title("Slice offset %.1f mm - drag to set window/level"
                            % self.sliceNode.GetSliceOffset())
        self.axes.grid(True, alpha=0.3)
        self.canvas.draw_idle()


def buildTissueSegmentation(volumeNode):
    """Create Brain / Skull and scalp / Background with built-in Segment Editor effects.

    Return the segmentation node and the IDs of the three segments.
    """
    segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentationNode", "MRHead tissues")
    segmentationNode.CreateDefaultDisplayNodes()
    segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
    segmentation = segmentationNode.GetSegmentation()

    segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
    segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
    segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
    segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
    segmentEditorWidget.setSegmentationNode(segmentationNode)
    segmentEditorWidget.setSourceVolumeNode(volumeNode)

    def applyEffect(segmentId, effectName, **parameters):
        segmentEditorNode.SetSelectedSegmentID(segmentId)
        segmentEditorWidget.setActiveEffectByName(effectName)
        effect = segmentEditorWidget.activeEffect()
        for name, value in parameters.items():
            effect.setParameter(name, str(value))
        effect.self().onApply()

    # Two scaffold segments, removed once the real segments are built.
    # "Image" covers every voxel so that "Background" stays inside the image.
    imageId = segmentation.AddEmptySegment("", "Image")
    applyEffect(imageId, "Threshold", MinimumThreshold=-10000, MaximumThreshold=10000)

    # "Head" is everything above the noise floor, closed up and de-speckled.
    headId = segmentation.AddEmptySegment("", "Head")
    applyEffect(headId, "Threshold", MinimumThreshold=30, MaximumThreshold=10000)
    applyEffect(headId, "Smoothing", SmoothingMethod="MORPHOLOGICAL_CLOSING", KernelSizeMm=5)
    applyEffect(headId, "Islands", Operation="KEEP_LARGEST_ISLAND")

    # "Brain": the interior of the head, shrunk away from the skull.
    brainId = segmentation.AddEmptySegment("", "Brain")
    applyEffect(brainId, "Logical operators", Operation="COPY", ModifierSegmentID=headId)
    applyEffect(brainId, "Margin", MarginSizeMm=-15)
    applyEffect(brainId, "Islands", Operation="KEEP_LARGEST_ISLAND")

    # "Skull and scalp": the outer shell that is left over.
    shellId = segmentation.AddEmptySegment("", "Skull and scalp")
    applyEffect(shellId, "Logical operators", Operation="COPY", ModifierSegmentID=headId)
    applyEffect(shellId, "Logical operators", Operation="SUBTRACT", ModifierSegmentID=brainId)

    # "Background": the air around the head, clipped to the image.
    backgroundId = segmentation.AddEmptySegment("", "Background")
    applyEffect(backgroundId, "Logical operators", Operation="COPY", ModifierSegmentID=imageId)
    applyEffect(backgroundId, "Logical operators", Operation="SUBTRACT", ModifierSegmentID=headId)

    segmentation.RemoveSegment(headId)
    segmentation.RemoveSegment(imageId)
    segmentEditorWidget.setActiveEffectByName(None)
    segmentEditorWidget = None
    slicer.mrmlScene.RemoveNode(segmentEditorNode)

    return segmentationNode, [brainId, shellId, backgroundId]


def collectStatistics(segmentationNode, volumeNode, segmentIds, maxSamples=20000):
    """Return a per-segment summary table, sampled voxel intensities, and segment colors."""
    import pandas as pd
    import SegmentStatistics

    statisticsLogic = SegmentStatistics.SegmentStatisticsLogic()
    parameterNode = statisticsLogic.getParameterNode()
    parameterNode.SetParameter("Segmentation", segmentationNode.GetID())
    parameterNode.SetParameter("ScalarVolume", volumeNode.GetID())
    parameterNode.SetParameter("LabelmapSegmentStatisticsPlugin.enabled", "True")
    parameterNode.SetParameter("ScalarVolumeSegmentStatisticsPlugin.enabled", "True")
    statisticsLogic.computeStatistics()
    statistics = statisticsLogic.getStatistics()

    segmentation = segmentationNode.GetSegmentation()
    names = {i: segmentation.GetSegment(i).GetName() for i in segmentIds}

    summary = pd.DataFrame([
        {
            "Segment": names[i],
            "Volume (cm3)": statistics[i, "LabelmapSegmentStatisticsPlugin.volume_mm3"] / 1000.0,
            "Mean": statistics[i, "ScalarVolumeSegmentStatisticsPlugin.mean"],
            "Median": statistics[i, "ScalarVolumeSegmentStatisticsPlugin.median"],
            "Std. dev.": statistics[i, "ScalarVolumeSegmentStatisticsPlugin.stdev"],
        }
        for i in segmentIds
    ])

    # The distribution plots get much slower, not more informative, with millions of points.
    rng = np.random.default_rng(0)
    volumeArray = slicer.util.arrayFromVolume(volumeNode)
    samples = []
    for i in segmentIds:
        mask = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, i, volumeNode)
        intensities = volumeArray[mask > 0]
        if intensities.size > maxSamples:
            intensities = rng.choice(intensities, maxSamples, replace=False)
        samples.append(pd.DataFrame({"Segment": names[i],
                                     "Intensity": intensities.astype(float)}))
    voxels = pd.concat(samples, ignore_index=True)

    palette = {names[i]: segmentation.GetSegment(i).GetColor() for i in segmentIds}
    return summary, voxels, palette


class SegmentStatisticsPlot:
    """Seaborn dashboard of segment statistics, shown next to the slice views."""

    def __init__(self, summary, voxels, palette):
        import seaborn as sns

        # "paper" context keeps the labels readable in a small layout pane.
        sns.set_theme(style="whitegrid", context="paper")
        self.figure = Figure(constrained_layout=True)

        axes = self.figure.subplots(1, 3)

        sns.violinplot(data=voxels, x="Segment", y="Intensity", hue="Segment",
                       palette=palette, legend=False, cut=0, inner="quartile",
                       ax=axes[0])
        axes[0].set_title("Intensity distribution")
        axes[0].set_xlabel("")

        sns.kdeplot(data=voxels, x="Intensity", hue="Segment", palette=palette,
                    fill=True, common_norm=False, alpha=0.4, ax=axes[1])
        axes[1].set_title("Intensity density")
        sns.move_legend(axes[1], "upper right", title=None, frameon=False, fontsize="small")

        sns.barplot(data=summary, x="Segment", y="Volume (cm3)", hue="Segment",
                    palette=palette, legend=False, ax=axes[2])
        for container in axes[2].containers:
            axes[2].bar_label(container, fmt="%.0f", fontsize="small")
        axes[2].set_title("Segment volume")
        axes[2].set_xlabel("")
        axes[2].margins(y=0.18)  # headroom for the bar labels

        # Angle the segment names so that they do not overlap in a narrow pane.
        for axis in (axes[0], axes[2]):
            for label in axis.get_xticklabels():
                label.set_rotation(20)
                label.set_horizontalalignment("right")

        self.canvas = view.showFigure(self.figure)

    def cleanup(self):
        """Remove the dashboard from the layout."""
        widget = view.viewWidget()
        if widget is not None and widget.figure() is self.figure:
            widget.setFigure(None)


def _mrHead():
    import SampleData

    volumeNode = SampleData.SampleDataLogic().downloadMRHead()
    slicer.util.setSliceViewerLayers(background=volumeNode, fit=True)
    return volumeNode


def showSliceHistogram(volumeNode=None, sliceViewName="Red"):
    """Show a histogram of the displayed slice that follows the slice view.

    Uses MRHead if ``volumeNode`` is not given. Return the :class:`SliceHistogramPlot`;
    keep a reference to it for as long as it should follow the slice view.
    """
    if volumeNode is None:
        volumeNode = _mrHead()
    return SliceHistogramPlot(volumeNode, sliceViewName)


def showSegmentStatistics():
    """Segment MRHead into three tissue classes and show their statistics with seaborn.

    Requires the ``seaborn`` and ``pandas`` packages. Return the
    :class:`SegmentStatisticsPlot` and the summary table.
    """
    volumeNode = _mrHead()
    segmentationNode, segmentIds = buildTissueSegmentation(volumeNode)
    summary, voxels, palette = collectStatistics(segmentationNode, volumeNode, segmentIds)
    # Hide the background segment in the slice views so the head stays readable.
    segmentationNode.GetDisplayNode().SetSegmentVisibility(segmentIds[2], False)
    plot = SegmentStatisticsPlot(summary, voxels, palette)
    slicer.util.resetSliceViews()
    return plot, summary
