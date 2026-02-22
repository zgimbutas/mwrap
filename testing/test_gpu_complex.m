function test_gpu_complex
% Test GPU complex double array passing via gpuArray.
% Requires: CUDA toolkit, mexcuda, GPU device.
% Run mwrap first:
%   ../mwrap -gpu -list -cppcomplex -mb -mex test_gpu_complex -c test_gpu_complex.cu test_gpu_complex.mw

mexcuda test_gpu_complex.cu

a = complex((1:7)', (7:-1:1)');
agpu = gpuArray(a);
bgpu = timestwo_complex(agpu);
b = gather(bgpu);
assert(norm(b - 2*a) < 1e-14, 'GPU complex timestwo failed');

fprintf('test_gpu_complex: PASSED\n');
