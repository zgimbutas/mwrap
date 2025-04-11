function test_char
% pass-fail test of the char- args and arrays.
% must do either make test_char_cpp or make test_char_c99 first.
% based on test_single.m, Barnett & Gimbutas 7/5/20-7/20/20.

tol = 2e-16;
tols = 1e-7;
%format long g  % for debug


%fprintf('scalar char routines...\n') % -------------------------------------
x = 1/3; ce = x+x; xs = single(x);

try
c = addchar(xs,xs);   % should error
catch ME
  assert(ME.message=='test_charmex: Invalid scalar argument, mxCHAR_CLASS expected')
end

a = '1'; b = '2'; ce = a+b;
c = addchar(a,b);
assert(norm(c-ce)<tol)
assert(class(c)=='double')



if( 1 == 2 ),
%FIXME: not implemented in mwrap 1.2, only scalar char is supported

%fprintf('vector char routines...\n') % -------------------------------------
x = x*ones(3,1); ce=x+x; xf = single(x);

try
c = arraddchar(xf,xf);   % should error
catch ME
  assert(ME.message=='test_charmex: Invalid array argument, mxCHAR_CLASS expected');
end

a = '12'; b = '23'; ce = a+b;
c = vecaddchar(a,b);
assert(abs(c-ce)<tol)
assert(class(c)=='double')

end
