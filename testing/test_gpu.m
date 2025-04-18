% test_gpu driver

mexcuda test_gpu.cu

a = ones(7,1)
agpu = gpuArray(a)
timestwo(agpu)
