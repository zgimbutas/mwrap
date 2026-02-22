% test_all_gpu - Run all GPU tests.
% Requires: CUDA toolkit, mexcuda, GPU device.
% Run mwrap first for each test (see individual test files for commands).

test_gpu;
test_gpu_complex;
test_gpu_int32;

fprintf('\nAll GPU tests PASSED.\n');
