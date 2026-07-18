function test_transfers

test_mult_inherit;
test_scopes;
test_literals;
test_types;
test_complex;
test_nulls;
test_method;
test_returns;
test_inputs;
test_outputs;
test_inouts;
test_mx;
test_const;
test_struct;

% ================================================================
% ================================================================
function test_mult_inherit

mex_id_ = 'c o Child* = new()';
[c] = test_transfersmex(mex_id_);
mex_id_ = 'c o int = c->Parent1.data1()';
[d1] = test_transfersmex(mex_id_, c);
mex_id_ = 'c o int = c->Parent2.data2()';
[d2] = test_transfersmex(mex_id_, c);
mex_id_ = 'c o int = c->Child.datas()';
[dd] = test_transfersmex(mex_id_, c);

tassert(d1 == 2, 'Multiple inheritance handling (1)');
tassert(d2 == 3, 'Multiple inheritance handling (2)');
tassert(dd == 3, 'Multiple inheritance handling (3)');

% ================================================================
function test_scopes;

mex_id_ = 'c o int = OuterClass::static_method()';
[x] = test_transfersmex(mex_id_);

tassert(x == 123, 'Access to static class method');

% ================================================================
function test_literals;

mex_id_ = 'c o int = literal_plus1(c i int)';
[y] = test_transfersmex(mex_id_, 7);
mex_id_ = 'c o int = strlen(c i cstring)';
[l] = test_transfersmex(mex_id_, 'Test');
tassert(y == 8, 'Integer literals');
tassert(l == 4, 'String literals');

% ================================================================
function test_types;


x = 0; xs = single(x); xc=char(42);
mex_id_ = 'takes_double(c i double&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_float(c i float&)';
test_transfersmex(mex_id_, xs);
mex_id_ = 'takes_long(c i long&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_int(c i int&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_char(c i char&)';
test_transfersmex(mex_id_, xc);
mex_id_ = 'takes_ulong(c i ulong&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_uint(c i uint&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_uchar(c i uchar&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_uchar(c i byte&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_bool(c i bool&)';
test_transfersmex(mex_id_, x);
mex_id_ = 'takes_size_t(c i size_t&)';
test_transfersmex(mex_id_, x);

mex_id_ = 'c o DerivedPair* = new()';
[dp] = test_transfersmex(mex_id_);
mex_id_ = 'c o double = dp->Pair.x()';
[x] = test_transfersmex(mex_id_, dp);
tassert(x == 7, 'Type casting');

% ================================================================
function test_complex;


zarray = rand(10,1) + 1i*rand(10,1);
n = length(zarray);
mex_id_ = 'c o cmplx = zsum(c i cmplx[], c i int)';
[result] = test_transfersmex(mex_id_, zarray, n);
tassert(abs(result-sum(zarray)) < 1e-10*norm(zarray), 'Complex support');


% ================================================================
function test_nulls;

mex_id_ = 'c o Pair* = null_pair()';
[p] = test_transfersmex(mex_id_);
tassert(p == 0, 'Null pointer return');

mex_id_ = 'c o int = is_null(c i Pair*)';
[flag] = test_transfersmex(mex_id_, p);
tassert(flag, 'Null pointer input');

mex_id_ = 'c o cstring = null_string()';
[s] = test_transfersmex(mex_id_);
tassert(s == 0, 'Null string return');

mex_id_ = 'c o char* = null_string()';
[c] = test_transfersmex(mex_id_);
tassert(isempty(c), 'Null scalar pointer return');

nil = [];
mex_id_ = 'c o int = is_null(c i double[])';
[flag] = test_transfersmex(mex_id_, nil);
tassert(flag, 'Null array input');

mex_id_ = 'c o char[x] = null_string()';
[ca] = test_transfersmex(mex_id_, 1);
tassert(isempty(ca), 'Null array return');

try
  mex_id_ = 'test_null_obj(c i Pair)';
test_transfersmex(mex_id_, p);
  tassert(0, 'Null argument dereference 1');
end
try
  mex_id_ = 'test_null_obj(c i Pair&)';
test_transfersmex(mex_id_, p);
  tassert(0, 'Null argument dereference 1');
end

try
  mex_id_ = 'c o double = p->Pair.x()';
[x] = test_transfersmex(mex_id_, p);
  tassert(0, 'Invalid this test');
end

mex_id_ = 'c o BadPair* = new()';
[bp] = test_transfersmex(mex_id_);
try
    mex_id_ = 'test_bad_pair(c i Pair*)';
test_transfersmex(mex_id_, bp);
  tassert(0, 'Invalid pointer test');
end
mex_id_ = 'delete(c i BadPair*)';
test_transfersmex(mex_id_, bp);


% ================================================================
function test_method;

x = 1;
y = 2;
mex_id_ = 'c o Pair* = new(c i double, c i double)';
[p] = test_transfersmex(mex_id_, x, y);
mex_id_ = 'c o double = p->Pair.x()';
[xx] = test_transfersmex(mex_id_, p);
mex_id_ = 'c o double = p->Pair.y()';
[yy] = test_transfersmex(mex_id_, p);
mex_id_ = 'delete(c i Pair*)';
test_transfersmex(mex_id_, p);
tassert(xx == 1, 'Method call');
tassert(yy == 2, 'Method call');


% ================================================================
function test_returns;

mex_id_ = 'c o Pair = test_return_obj()';
[p1] = test_transfersmex(mex_id_);
tassert(sscanf(p1, 'Pair:%x') > 0, 'Return object');

mex_id_ = 'c o double[x] = test_return_array(c i Pair&)';
[xy] = test_transfersmex(mex_id_, p1, 2);
tassert(norm(xy-[1.5; 2.5]) == 0, 'Return array');

mex_id_ = 'c o double[x] = test_return_array2(c i Pair&)';
[xy] = test_transfersmex(mex_id_, p1, 2);
tassert(norm(xy-[1.5; 2.5]) == 0, 'Return array');

mex_id_ = 'c o double = test_return_scalar(c i double[])';
[sum] = test_transfersmex(mex_id_, xy);
tassert(sum == 4, 'Return scalar');

xy_z = [1+5i, 7+11i];
mex_id_ = 'c o cmplx = test_return_zscalar(c i cmplx[])';
[sum1] = test_transfersmex(mex_id_, xy);
mex_id_ = 'c o cmplx = test_return_zscalar(c i cmplx[])';
[sum2] = test_transfersmex(mex_id_, xy_z);
tassert(sum1 == 4,     'Return zscalar (reals)');
tassert(sum2 == 8+16i, 'Return zscalar (complexes)');

mex_id_ = 'c o cstring = test_return_string()';
[s] = test_transfersmex(mex_id_);
tassert(strcmp(s, 'Hello, world!'), 'Return string');

mex_id_ = 'c o Pair* = test_return_p_obj()';
[p2] = test_transfersmex(mex_id_);
mex_id_ = 'c o double[x] = test_return_array(c i Pair&)';
[xy] = test_transfersmex(mex_id_, p2, 2);
tassert(norm(xy - [3;5]) == 0, 'Return obj*');

a = 7; b = 11;
mex_id_ = 'c o int* = test_return_p_scalar(c i int*, c i int*)';
[z1] = test_transfersmex(mex_id_, a, b);
tassert(z1 == 11, 'Return scalar*');

a_z = 7 + 10i; b_z = 11 + 15i;
mex_id_ = 'c o cmplx* = test_return_p_zscalar(c i cmplx*, c i cmplx*)';
[z1] = test_transfersmex(mex_id_, a, b);
mex_id_ = 'c o cmplx* = test_return_p_zscalar(c i cmplx*, c i cmplx*)';
[z2] = test_transfersmex(mex_id_, a_z, b_z);
tassert(z1 == 11, 'Return zscalar*');
tassert(z2 == 11 + 15i, 'Return zscalar*');

mex_id_ = 'c o Pair& = test_return_r_obj(c i Pair&)';
[p2c] = test_transfersmex(mex_id_, p2);
tassert(strcmp(p2, p2c), 'Return obj&');

mex_id_ = 'c o int& = test_return_r_scalar(c i int&, c i int&)';
[z2] = test_transfersmex(mex_id_, a, b);
tassert(z2 == 11, 'Return scalar&');

mex_id_ = 'c o cmplx& = test_return_r_zscalar(c i cmplx&, c i cmplx&)';
[z2] = test_transfersmex(mex_id_, a, b);
mex_id_ = 'c o cmplx& = test_return_r_zscalar(c i cmplx&, c i cmplx&)';
[z3] = test_transfersmex(mex_id_, a_z, b_z);
tassert(z2 == 11, 'Return zscalar&');
tassert(z3 == 11 + 15i, 'Return zscalar&');

mex_id_ = 'delete(c i Pair*)';
test_transfersmex(mex_id_, p1);
mex_id_ = 'delete(c i Pair*)';
test_transfersmex(mex_id_, p2);


% ================================================================
function test_inputs

x = 101; y = 202;
mex_id_ = 'c o Pair* = new(c i double, c i double)';
[p] = test_transfersmex(mex_id_, x, y);
mex_id_ = 'c o double = test_input_obj(c i Pair)';
[sum] = test_transfersmex(mex_id_, p);
tassert(sum == 303, 'Input obj');

xy = [11, 22];
mex_id_ = 'c o double = test_input_array(c i double[x])';
[sum] = test_transfersmex(mex_id_, xy, 2);
tassert(sum == 33, 'Input array');

mex_id_ = 'c o double = test_input_array2(c i double[x])';
[sum] = test_transfersmex(mex_id_, xy, 2);
tassert(sum == 33, 'Input array');

xy_z = [11 + 5i, 22 + 6i];
mex_id_ = 'c o cmplx = test_input_zarray(c i cmplx[x])';
[sum] = test_transfersmex(mex_id_, xy, 2);
mex_id_ = 'c o cmplx = test_input_zarray(c i cmplx[x])';
[sum2] = test_transfersmex(mex_id_, xy_z, 2);
tassert(sum == 33, 'Input zarray');
tassert(sum2 == 33 + 11i, 'Input zarray');

mex_id_ = 'c o int = test_input_scalar(c i int)';
[xp1] = test_transfersmex(mex_id_, x);
tassert(xp1 == 102, 'Input scalar');

x_z = 101 + 99i;
mex_id_ = 'c o cmplx = test_input_zscalar(c i cmplx)';
[xp1] = test_transfersmex(mex_id_, x);
mex_id_ = 'c o cmplx = test_input_zscalar(c i cmplx)';
[xp1z] = test_transfersmex(mex_id_, x_z);
tassert(xp1 == 102, 'Input zscalar');
tassert(xp1z == 102 + 99i, 'Input zscalar');

msg = 'Hello, world!';
mex_id_ = 'c o int = test_input_string(c i cstring)';
[msglen] = test_transfersmex(mex_id_, msg);
tassert(msglen == length(msg), 'Input string');

mex_id_ = 'c o double = test_input_p_obj(c i Pair*)';
[sum2] = test_transfersmex(mex_id_, p);
tassert(sum2 == 303, 'Input obj*');

mex_id_ = 'c o int = test_input_p_scalar(c i int*)';
[xp1b] = test_transfersmex(mex_id_, x);
tassert(xp1b == 102, 'Input scalar*');

mex_id_ = 'c o cmplx = test_input_p_zscalar(c i cmplx*)';
[xp1b] = test_transfersmex(mex_id_, x);
mex_id_ = 'c o cmplx = test_input_p_zscalar(c i cmplx*)';
[xp1c] = test_transfersmex(mex_id_, x_z);
tassert(xp1b == 102, 'Input zscalar*');
tassert(xp1c == 102 + 99i, 'Input zscalar*');

mex_id_ = 'c o double = test_input_r_obj(c i Pair&)';
[sum3] = test_transfersmex(mex_id_, p);
tassert(sum3 == 303, 'Input obj&');

mex_id_ = 'c o int = test_input_r_scalar(c i int&)';
[xp1c] = test_transfersmex(mex_id_, x);
tassert(xp1c == 102, 'Input scalar&');

mex_id_ = 'c o cmplx = test_input_r_zscalar(c i cmplx&)';
[xp1c] = test_transfersmex(mex_id_, x);
mex_id_ = 'c o cmplx = test_input_r_zscalar(c i cmplx&)';
[xp1d] = test_transfersmex(mex_id_, x_z);
tassert(xp1c == 102, 'Input scalar&');
tassert(xp1d == 102 + 99i, 'Input scalar&');

mex_id_ = 'delete(c i Pair*)';
test_transfersmex(mex_id_, p);


% ================================================================
function test_outputs

mex_id_ = 'test_output_array(c o double[x])';
[xy] = test_transfersmex(mex_id_, 2);
tassert(norm(xy-[1;2]) == 0, 'Output array');

mex_id_ = 'test_output_rarray(c o doubler)';
[xyr] = test_transfersmex(mex_id_, 2);
tassert(norm(xyr-[7;11]) == 0, 'Output rarray');

mex_id_ = 'test_output_rarray2(c o doubler)';
[xyr2] = test_transfersmex(mex_id_, 2);
tassert(isempty(xyr2), 'Output rarray');

mex_id_ = 'test_output_zarray(c o cmplx[x])';
[xy] = test_transfersmex(mex_id_, 2);
mex_id_ = 'test_output_zarray2(c o cmplx[x])';
[xy_z] = test_transfersmex(mex_id_, 2);
tassert(norm(xy-[1;2]) == 0, 'Output array');
tassert(norm(xy_z-[1+3i;2]) == 0, 'Output array');

fmt = '= %d'; i = 101;
mex_id_ = 'snprintf(c o cstring[x], c i int, c i cstring, c i int)';
[buf] = test_transfersmex(mex_id_, 128, fmt, i, 128);
tassert(strcmp('= 101', buf), 'Output string');

mex_id_ = 'test_output_p_scalar(c o int*)';
[i2] = test_transfersmex(mex_id_);
tassert(i2 == 202, 'Output scalar*');

mex_id_ = 'test_output_p_zscalar(c o cmplx*)';
[z2] = test_transfersmex(mex_id_);
tassert(z2 == 202+303i, 'Output zscalar*');

mex_id_ = 'test_output_r_scalar(c o int&)';
[i3] = test_transfersmex(mex_id_);
tassert(i3 == 303, 'Output scalar&');

mex_id_ = 'test_output_r_zscalar(c o cmplx&)';
[z3] = test_transfersmex(mex_id_);
tassert(z3 == 303+404i, 'Output zscalar&');


% ================================================================
function test_inouts

xy = [1, 2];
mex_id_ = 'test_inout_array(c io double[])';
[xy] = test_transfersmex(mex_id_, xy);
tassert(norm(xy - [2,3]) == 0, 'Inout array');

s1 = 'foo'; 
s2 = 'bar';
mex_id_ = 'strcat(c io cstring[x], c i cstring)';
[s1] = test_transfersmex(mex_id_, s1, s2, 128);
tassert(strcmp(s1, 'foobar'), 'Inout string');

i1 = 101;
mex_id_ = 'test_inout_p_scalar(c io int*)';
[i1] = test_transfersmex(mex_id_, i1);
tassert(i1 == 303, 'Inout scalar*');

i2 = 101;
mex_id_ = 'test_inout_r_scalar(c io int&)';
[i2] = test_transfersmex(mex_id_, i2);
tassert(i2 == 404, 'Inout scalar&');


% ================================================================
function test_mx


in1 = 42;
mex_id_ = 'c o double = test_mx_input(c i mxArray)';
[out1] = test_transfersmex(mex_id_, in1);
tassert(out1 == 42, 'Input mx');

mex_id_ = 'test_mx_output(c o mxArray)';
[out2] = test_transfersmex(mex_id_);
tassert(strcmp(out2, 'foobar'), 'Output mx');

mex_id_ = 'c o mxArray = test_mx_return()';
[out3] = test_transfersmex(mex_id_);
tassert(out3 == 42, 'Return mx');


% ================================================================
function test_const

mex_id_ = 'c o int = identity(c i const TEST_CONST)';
[result] = test_transfersmex(mex_id_, 0);
tassert(result == 42, 'Constant transfer');
mex_id_ = 'c o int = identity(c i const TEST_CONST)';
[result2] = test_transfersmex(mex_id_, 0);
tassert(result2 == 42, 'Constant transfer');

% ================================================================
function test_struct



xy1 = [1, 2];
mex_id_ = 'unpack_struct(c i my_struct_t&, c o double[x])';
[xy2] = test_transfersmex(mex_id_, xy1, 2);
tassert(norm(xy2-[1;2]) == 0, 'Structure conversion on input');

mex_id_ = 'pack_struct(c o my_struct_t, c i double[])';
[xy3] = test_transfersmex(mex_id_, xy1);
tassert(norm(xy3-[1;2]) == 0, 'Structure conversion on output');

xy4 = [3; 4];
mex_id_ = 'swap_struct(c io my_struct_t)';
[xy4] = test_transfersmex(mex_id_, xy4);
tassert(norm(xy4-[4; 3]) == 0, 'Structure on inout');

mex_id_ = 'c o my_struct_t& = rightmost(c i my_struct_t&, c i my_struct_t&)';
[result] = test_transfersmex(mex_id_, xy1, xy4);
tassert(norm(result-[4;3]) == 0, 'Structure on reference return');

mex_id_ = 'c o my_struct_t* = add1(c i my_struct_t&)';
[xy5] = test_transfersmex(mex_id_, xy4);
tassert(norm(xy5-[5;4]) == 0, 'Structure on pointer return');

mex_id_ = 'c o int = get_my_struct_allocs()';
[alloc_count] = test_transfersmex(mex_id_);
tassert(alloc_count == 0, 'Balanced allocations in structure management');

% ================================================================
function tassert(pred, msg)

if ~pred, fprintf('Failure: %s\n', msg); end

