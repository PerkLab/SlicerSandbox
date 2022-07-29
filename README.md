# SlicerSandbox
![Logo](Sandbox_Logo_128.png)

Collection of modules for 3D Slicer, which are already useful, but not finalized, polished, or proven to be useful enough to be included in Slicer core.
- Auto Save: automatically save the scene at specified time intervals.
- [Characterize Transform Matrix](#characterize-transform-matrix): quick geometric interpretations of a transformation matrix
- Combine Models: Boolean operations(union, intersection, difference) for models.
- [Curved Planar Reformat](#curved-planar-reformat): straighten vessels, bones, or other structures for easier visualization, quantification, creating panoramic dental X-ray, etc.
- Documentation Tools: tools for creating documentation on read-the-docs. It can generate html documentation from a Slicer source tree, convert module documentation from MediaWiki to markdown, etc.
- Import OCT: Load Topcon OCT image file (`*.fda`).
- Import Osirix ROI: Load Osirix ROI files as segmentation.
- Import SliceOmatic: Load SliceOmatic segmentation files.
- [Lights](#lights): customize lighting in 3D views.
- Line Profile: compute and plot image intensity profile along a line.
- Scene Recorder: record all MRML node change events into a json document.
- Segment Cross-Section Area: Measure cross-section of a segmentation along one of its axis. Note there are more advanced tools for this now in [Segment Geometry](https://github.com/jmhuie/Slicer-SegmentGeometry) and [SlicerVMTK](https://github.com/vmtk/SlicerExtension-VMTK#the-vmtk-extension-for-3d-slicer) extensions.
- Style Tester: test Qt style sheet changes.
- User Statistics: collect statistics about what modules and tools are used and for how long.
- Volume Rendering Special Effects: custom shaders for special volume rendering effects.

## Lights

This module can be used to adjust lighting and rendering options in 3D views. Select all or specific 3D views at the top, then adjust options in sections below.

- Lighting: configures a [lightkit](https://vtk.org/doc/nightly/html/classvtkLightKit.html) that is used for rendering of all 3D content, including volume rendering. The kit consists of the key light (typically the strongest light, simulating overhead lighting, such as ceiling lights or sun), fill light (typically same side as key light, but other side; simulating diffuse reflection of key light), headlight (moves with the camera, reduces contrast between key light and fill light), back lights (fill on the high-contrast areas behind the object). [**Short demo video**](https://youtu.be/rQZ9enRbn0w)
- Ambient shadows: Uses screen space ambient occlusion (SSAO) method to simulate shadows. Size scale determines the details that are emphasized. The scale is logarithmic, the default 0 value corresponds to 100mm. For highlighting smaller details (such as uneven surface), reduce the value. Use larger values to make large objects better distinguishable. These settings have no effect on volume rendering.
- Image-based lighting: Necessary when models are displayed with PBR (physics based rendering) interpolation. Brightness of the image determines the amount of light reflected from object surfaces; and fragments of the image appears as reflection on surface of smooth metallic objects. Currently only a single picture is provided via the user interface ([hospital_room](https://github.com/PerkLab/SlicerSandbox/blob/master/Lights/Resources/hospital_room.jpg)), but other images can be downloaded (for example from [polyhaven.com](https://polyhaven.com)) and be used in the Python API of the module. These settings have no effect on volume rendering. See some examples [here](https://discourse.slicer.org/t/new-feature-basic-support-for-physically-based-rendering-pbr/21725).

![](https://aws1.discourse-cdn.com/standard17/uploads/slicer/optimized/2X/d/d3bbe21f7cd59394cf9bd00e6bb513ba6fba30e0_2_1035x628.jpeg)

## Remove CT table

Remove patient table from CT images fully automatically, by blanking out (filling with -1000 HU) voxels that are not included in an automatically determined convex-shaped region of interest.

If boundary of the extracted region is chipped away in the output image then either add a fixed-size `padding` and/or increase the computation `accuracy` (in `Advanced` section).

![](RemovePatientTable.jpg)

## Curved Planar Reformat

Curved planar reformat module allows "straightening" a curved volume for visualization or quantification. The module provides two-way spatial mapping between the original and straightened space.

### Adjust reformatting parameters for robust mapping

If the slice size is too large or curve resolution is too fine then in some regions you can have transform that maps the same point into different positions (the displacement field folds into itself). In these regions the transforms in not invertible.

To reduce these ambiguously mapped regions, decrease `Slice size`. If necessary `Curve resolution` can be slightly increased as well (it controls how densely the curve is sampled to generate the displacement field, if samples are farther from each other then it may reduce chance of contradicting samples).

![image|561x379](https://aws1.discourse-cdn.com/standard17/uploads/slicer/original/2X/3/3c6ee214e10415a6eb1fb53638c02e44bc93d4a1.png)

You can quickly validate the transform, by going to Transforms module and in Display/Visualization section check all 3 checkboxes, the straightened image as `Region` and visualization mode to `Grid`.

For example, this transform results in a smooth displacement field, it is invertible in the visualized region:

![image|690x420](https://aws1.discourse-cdn.com/standard17/uploads/slicer/optimized/2X/0/045048696d683fffafbea801edeb05cc1349abd5_2_1035x630.png)

If the slice size is increased then folding occurs:

![image|489x500](https://aws1.discourse-cdn.com/standard17/uploads/slicer/optimized/2X/e/e6c2b020c07ed52c5b37b665bf424d9e82738cd0_2_733x750.png)

Probably you can find a parameter set that works for a large group of patients. Maybe one parameter set works for all, but maybe you need to have a few different presets (small, medium, large)

## Characterize Transform Matrix

It is often difficult to understand what a transform matrix is doing just by inspection.  All the information is in those 12 numbers, but not in an easily understood format. CharacterizeTransformMatrix is a simple utility module which tries to quickly give you any information you might want to know about what a transformation matrix is doing.  For example, is it a rigid transformation or is there scaling?  If there is scaling, what are the scale factors and stretch directions?  Is there rotation?  If so, what is the axis of rotation and how much rotation occurs around that axis?  Alternatively, if we break down the rotation into a sequence of rotations around coordinate axes, what is the rotation about each axis?

### To use
Open the module and select the transform node you want to know about.  An analysis such as the following will appear in the text box below:

```
Scale factors and stretch directions (eigenvalues and eigenvectors of stretch matrix K):
  f0: +0.012% change in direction [1.00, 0.03, -0.08]
  f1: -2.843% change in direction [-0.08, -0.10, -0.99]
  f2: +3.248% change in direction [0.04, -0.99, 0.10]
This transform is not rigid! Total volume changes by +0.325%, and maximal change in one direction is +3.248%
The rotation matrix portion of this transformation rotates 15.0 degrees ccw (if you look in the direction the vector points) around a vector which points to [0.76, -0.59, -0.27] (RAS)
Broken down into a series of rotations around axes, the rotation matrix portion of the transformation rotates 
  11.8 degrees ccw around the positive R axis, then 
  8.4 degrees cw around the positive A axis, then 
  5.0 degrees cw around the positive S axis
Lastly, this transformation translates, shifting:
  +194.2 mm in the R direction
  +73.4 mm in the A direction
  -1170.3 mm in the S direction
```
This analysis is for the matrix 
```
0.985821 0.0570188 -0.157817 194.155 
-0.0873217 1.01 -0.192319 73.4412 
0.14329 0.203373 0.94 -1170.25 
0 0 0 1 
```
### Some Decomposition Details
This module uses polar decomposition to describe the components of a 4x4 transform matrix. The decomposition has the form: `H = T * R * K`, where `H` is the full homogeneous transformation matrix (with 0,0,0,1 as the bottom row), `T` is a translation-only matrix, `R` is a rotation-only matrix, and `K` is a stretch matrix. `K` can further be decompsed into three scale matrices, which can each be characterized by a stretch direction (an eigenvector) and a stretch factor (the associated eigenvalue). Points to be transformed are on the right, so the order of operations is stretching first, then rotation, then translation. 

If you would like access to the decomposed components of the matrix, you can call the relevant logic function of this module as follows: 
```
import CharacterizeTransformMatrix 
decompositionResults = CharacterizeTransformMatrix.CharacterizeTransformMatrixLogic().characterizeLinearTransformNode(transformNode)
```
`decompositionResults` will then be a namedTuple with all the information from the decomposition. For example, `decompositionResults.rotationAngleDegrees` will have the angle the transformation rotates by around the rotation axis.  The named fields of the results are

|Field Name| Description|
| ----------- | ----------- |
| textResults | a line by line list of the analysis text |
| isRigid | boolean, true if largest strech % change is less that 0.1% |
| scaleFactors | numpy vector of scale factors in eigendirections of stretch matrix (with a 4th element which is always 1) |
|scaleDirections| list of 3 scale directions as 4 element vectors (4th element always 0)|
|largestPercentChangeScale | largest scale factor as a percent change (100 * (scaleFactor-1)) |
|volumePercentChangeOverall| total volume % change after all stretching/shrinking|
|scipyRotationObject| scipy `Rotation` object of the rotation component of the transform|
|rotationAxis | RAS vector describing the axis the transform rotates about|
|rotationAngleDegrees| positive if counterclockwise when looking down axis|
|eulerAnglesRAS | sequence of rotation angles about the Right, Anterior, and then Superior axes|
|translationVector| 3-element vector of RAS translation|
|translationOnlyMatrix| identitiy matrix with translation vector in 4th column|
|rotationOnlyMatrix|4x4 rotation matrix `R` from the decomposition|
|stretchOnlyMatrix|4x4 stretch matrix `K` from the decomposition|
|scaleMatrixList|list of three 4x4 symmetric (likely non-uniform) scale matrices (`S1*S2*S3=K`)|
|stretchEigenvectorMatrix|4x4 matrix with the stretch direction eigenvectors as the first 3 columns|

