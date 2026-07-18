function test_catch


try
  mex_id_ = 'toss()';
test_catchmex(mex_id_);
  disp('Failed to properly catch exception');
catch
  fprintf('Correctly caught message: %s\n', lasterr);
end
