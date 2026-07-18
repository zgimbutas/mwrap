function c=arraddz(a,b)
n = numel(a);
mex_id_ = 'arraddz(c i dcomplex[x], c i dcomplex[x], c o dcomplex[x], c i int)';
[c] = test_singlemex(mex_id_, a, b, n, n, n, n);

