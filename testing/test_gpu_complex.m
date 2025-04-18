% test_gpu_complex driver

mexcuda test_gpu_complex.cu

a = complex(ones(7,1))
agpu = gpuArray(a)
timestwo_complex(agpu)
