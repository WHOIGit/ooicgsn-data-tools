function t = nc_reader(filename)
% NC_READER Read a NetCDF file, extract data and save as a timetable.
% 
% Code based on example available from Mathworks at:
% https://www.mathworks.com/help/parallel-computing/examples/process-big-data-in-the-cloud.html

% Get information about the NetCDF data file
fileInfo = ncinfo(filename);

% Extract the global and variable level attributes -- note, Matlab doesn't
% really support these very well, so their utility is limited.
%gAttributes = struct2table(fileInfo.Attributes);
vAttributes = {fileInfo.Variables.Attributes};

% Extract the variable names
varNames = string({fileInfo.Variables.Name});

% test for presence of a variable called time
i = 1; test = 0;
while test == 0 && i <= numel(varNames)
    test = strcmp('time', varNames{i});
    i = i + 1;
end %while
if ~test
    error('The NetCDF file specified does not include the variable ''time''')
end %if
clear i test

% Create the datetime axis from the time variable (OMS++ uses 1970 and OOI
% uses 1900 as their pivot years).
nc_time = ncread(filename, 'time');   % obtain the time record
test = nc_time(1) / 60 / 60 / 24 + datenum(1970, 1, 1, 0, 0, 0);
if test > now
    nc_time = nc_time / 60 / 60 / 24 + datenum(1900, 1, 1, 0, 0, 0);
else 
    nc_time = nc_time / 60 / 60 / 24 + datenum(1970, 1, 1, 0, 0, 0);
end %if
dt = datetime(nc_time, 'ConvertFrom', 'datenum', 'TimeZone', 'UTC');
rowlength = length(dt);
clear test nc_time

% Create an empty timetable using the datetime axis
t = timetable('RowTimes', dt);

% Populate the timetable with the variable data
for k = 1:numel(varNames)
    % skip adding time (already added as the RowTime) and obs
    if strcmp(varNames{k}, 'time') || strcmp(varNames{k}, 'obs')
        continue
    end %if
    % read the variable from the NetCDF file
    data = ncread(filename, varNames{k});
    if ~isempty(vAttributes{k})
        attr = struct2table(vAttributes{k});
        units = {''}; descr = {''};
        for j = 1:height(attr)
            if strcmp(attr.Name(j), 'units')
                units = attr.Value(j);
            end %if
            if strcmp(attr.Name(j), 'comment')
                descr = attr.Value(j);
            end %if
        end %for
    end %if
    [r, c] = size(data);    % check the dimensions
    if r == rowlength
        % if the number of rows == the number of RowTimes, add the variable
        % without modification.
        t = addvars(t, data, 'NewVariableNames', varNames{k});
        t.Properties.VariableUnits{varNames{k}} = units{:};
        t.Properties.VariableDescriptions{varNames{k}} = descr{:};
    elseif c == rowlength
        % if the number of columns equals the RowTimes, rotate the variable
        % before adding it so the row length matches the RowTimes
        t = addvars(t, data', 'NewVariableNames', varNames{k});
        t.Properties.VariableUnits{varNames{k}} = units{:};
        t.Properties.VariableDescriptions{varNames{k}} = descr{:};
    elseif r == 1 && c == 1
        % this is a scalar variable, and it needs to replicated out to the
        % RowTimes dimension before it can be added.
        t = addvars(t, repmat(data, rowlength, 1), 'NewVariableNames', varNames{k});
        t.Properties.VariableUnits{varNames{k}} = units{:};
        t.Properties.VariableDescriptions{varNames{k}} = descr{:};        
    else
        % this is something weird, ignore it for now.
    end %if
end %for
clear dt rowlength k data r c
end %function