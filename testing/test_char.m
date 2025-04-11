function test_char
% pass-fail test of the char- args and arrays.
% must do either make test_char_cpp or make test_char_c99 first.
% based on test_single.m, Barnett & Gimbutas 7/5/20-7/20/20.


%fprintf('scalar real routines...\n') % -------------------------------------
x = 1/3; ce = x+x; xc = single(x);

try
c = addchar(xc,xc);   % should error
catch ME
  assert(ME.message=='test_charmex: Invalid scalar argument, mxCHAR_CLASS expected')
end

try
c = arraddchar(xc,xc);   % should error
catch ME
  assert(ME.message=='test_charmex: Invalid array argument, mxDOUBLE_CLASS expected');
end
