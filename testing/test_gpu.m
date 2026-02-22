function test_gpu
% Test GPU double array passing via gpuArray.
% Requires: CUDA toolkit, mexcuda, GPU device.
% Run mwrap first:
%   ../mwrap -gpu -list -cppcomplex -mb -mex test_gpu -c test_gpu.cu test_gpu.mw

mexcuda test_gpu.cu

a = (1:7)';
agpu = gpuArray(a);
bgpu = timestwo(agpu);
b = gather(bgpu);
assert(norm(b - 2*a) == 0, 'GPU double timestwo failed');

fprintf('test_gpu: PASSED\n');
