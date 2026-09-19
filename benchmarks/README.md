# Inference benchmarks

`trankit_dual_device_benchmark_app.py` compares inference execution configurations. `build_trankit_xlmr_onnx_cpu.py` prepares an ONNX CPU experiment. Run them as `python -m benchmarks.<module>` from the repository root.

These tools require model artifacts and the corresponding inference libraries. They are performance workspaces, not CI assertions; measurements depend on hardware, model configuration, and input data.
