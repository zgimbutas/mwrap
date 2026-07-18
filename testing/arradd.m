function c=arradd(a,b)
n = numel(a);
mex_id_ = 'arradd(c i double[x], c i double[x], c o double[x], c i int)';
[c] = test_singlemex(mex_id_, a, b, n, n, n, n);

