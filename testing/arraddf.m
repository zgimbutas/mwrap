function c=arraddf(a,b)
n = numel(a);
mex_id_ = 'arraddf(c i float[x], c i float[x], c o float[x], c i int)';
[c] = test_singlemex(mex_id_, a, b, n, n, n, n);


% COMPLEX=========================================================

% scalar complex.........

