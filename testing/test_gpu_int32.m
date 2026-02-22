function test_gpu_int32
% Test GPU int32 array passing via gpuArray.
% Requires: CUDA toolkit, mexcuda, GPU device.
% Run mwrap first:
%   ../mwrap -gpu -list -cppcomplex -mb -mex test_gpu_int32 -c test_gpu_int32.cu test_gpu_int32.mw

mexcuda test_gpu_int32.cu

a = int32((1:7)');
agpu = gpuArray(a);
bgpu = timestwo_gpu_int32(agpu);
b = gather(bgpu);
assert(norm(double(b) - 2*double(a)) == 0, 'GPU int32 timestwo failed');

fprintf('test_gpu_int32: PASSED\n');
