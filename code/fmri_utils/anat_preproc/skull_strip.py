from nipype.interfaces import fsl as fsl



def structural_skull_strip(reorient_file , out_file):
    skull_stripper = fsl.BET()
    skull_stripper.inputs.in_file = reorient_file
    skull_stripper.inputs.out_file = out_file
    skull_stripper.inputs.frac = 0.3
    skull_stripper.inputs.reduce_bias = True
    skull_stripper.inputs.vertical_gradient = .05
    skull_stripper.cmdline
    SS_results = skull_stripper.run()
    return SS_results
