function c=arraddc(a,b)
n = numel(a);
mex_id_ = 'arraddc(c i fcomplex[x], c i fcomplex[x], c o fcomplex[x], c i int)';
[c] = test_singlemex(mex_id_, a, b, n, n, n, n);
