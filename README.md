# SlicerSandbox
![Logo](Sandbox_Logo_128.png)

Collection of utilities that are not polished implementations but may still be useful as they are.


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
