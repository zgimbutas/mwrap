% test_gpu driver
% ../mwrap -gpu -list -cppcomplex -mb -mex test_gpu_int32 -c test_gpu_int32.cu test_gpu_int32.mw

mexcuda test_gpu_int32.cu

a = ones(7,1,'int32')
agpu = gpuArray(a)
timestwo_gpu_int32(agpu)

% test_cpu driver
% ../mwrap -list -cppcomplex -mb -mex test_cpu_int32 -c test_cpu_int32.cc test_cpu_int32.mw

mex test_cpu_int32.cc

a = ones(7,1,'int32')
timestwo_cpu_int32(a)
