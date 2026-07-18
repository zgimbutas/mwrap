function test_fortran1


mex_id_ = 'foo(c o int*, c i int, c i int)';
[a] = test_fortran1mex(mex_id_, 1, 2);
tassert(a == 3, 'FORTRAN bindings');

function tassert(pred, msg)
if ~pred, fprintf('Failure: %s\n', msg); end
