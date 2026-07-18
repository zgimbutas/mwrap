function c=add(a,b)
mex_id_ = 'add(c i double, c i double, c o double[x])';
[c] = test_singlemex(mex_id_, a, b, 1);

