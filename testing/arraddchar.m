function c=arraddchar(a,b)
n = numel(a);
mex_id_ = 'arraddchar(c i char[x], c i char[x], c o char[x], c i int)';
[c] = test_charmex(mex_id_, a, b, n, n, n, n);

