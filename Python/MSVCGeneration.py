
#
# --- MIT Open Source License --------------------------------------------------
# PiB - Python Build System
# Copyright (C) 2011 by Don Williamson
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ------------------------------------------------------------------------------
#
# MSVCGeneration.py: Automatic, dependency-based generation of Visual Studio C++
# 2005/2008 Projects and Solutions
#

import os
import uuid
import hashlib
import base64
import sys
import Utils


class MSVCGeneration2005:
    VisualStudio = "2005"
    Solution = "9.00"
    Project = "8.00"

class MSVCGeneration2008:
    VisualStudio = "2008"
    Solution = "10.00"
    Project = "9.00"


def SolutionHeader():
    
    # Determine the current version using the exact same logic that drives the compilation
    version = MSVCGeneration2005
    if os.getenv("VS90COMNTOOLS"):
        version = MSVCGeneration2008
        
    header = """Microsoft Visual Studio Solution File, Format Version {0}
# Visual Studio {1}"""
    header = header.format(version.Solution, version.VisualStudio)
    return header

def ProjectHeader():
    # Determine the current version using the exact same logic that drives the compilation
    version = MSVCGeneration2005
    if os.getenv("VS90COMNTOOLS"):
        version = MSVCGeneration2008
        
    header = """<VisualStudioProject
    ProjectType="Visual C++"
    Version="{0}"
    Name="%NAME%"
    ProjectGUID="{%GUID%}"
    RootNamespace="%NAME%"
    Keyword="Win32Proj"
    >
    <Platforms>
        <Platform
            Name="Win32"
        />
    </Platforms>
    <ToolFiles>
    </ToolFiles>"""
    header = header.replace("{0}", version.Project)
    return header


vcproj_config = """		<Configuration
            Name="%CONFIG%|Win32"
            OutputDirectory="%OUTPUTDIR%"
            IntermediateDirectory="%INTERDIR%"
            ConfigurationType="0"
            CharacterSet="1"
            >
            <Tool
                Name="VCNMakeTool"
                BuildCommandLine="%BUILD%"
                ReBuildCommandLine="%REBUILD%"
                CleanCommandLine="%CLEAN%"
                Output="%OUTPUT%"
                PreprocessorDefinitions=""
                IncludeSearchPath="%INCLUDESEARCH%"
                ForcedIncludes=""
                AssemblySearchPath=""
                ForcedUsingAssemblies=""
                CompileAsManaged=""
            />
        </Configuration>"""

def CreateFolderLists(dict):

    # Gather a list of folders first
    folders = [ ]
    for dir, content in dict.items():
        if content != None:
            folders += [ (dir, CreateFolderLists(content)) ]

    # Followed by a list of files
    files = [ ]
    for dir, content in dict.items():
        if content == None:
            files += [ (dir, None) ]

    folders = sorted(folders)
    files = sorted(files)

    return folders + files


def WriteProjectFiles(f, tab, name, entries):

    # Write file markup if this is a file
    if entries == None:
        print(tab + "<File", file=f)
        print(tab + '\tRelativePath="' + name + '"', file=f)
        print(tab + "\t>", file=f)
        print(tab + "</File>", file=f)
        return

    # Open a filter tag if this is a named folder
    if name != "":
        print(tab + "<Filter", file=f)
        tab += "\t"
        print(tab + 'Name="' + name + '"', file=f)
        print(tab + 'UniqueIdentifier="{' + str(uuid.uuid1()) + '}"', file=f)
        print(tab + ">", file=f)

    # Recurse into the entries of this folder
    for entry in entries:
        WriteProjectFiles(f, tab, entry[0], entry[1])

    # Close the filter tag
    if name != "":
        print(tab[:-1] + "</Filter>", file=f)


def DoesProjectNeedUpdating(vcproj_path, files):

    # Hash all the inputs
    md5 = hashlib.md5()
    for file in files:
        md5.update(bytes(file, "utf-8"))
    
    src_digest = md5.digest()
    src_digest = base64.urlsafe_b64encode(src_digest)
    src_digest = bytes(src_digest).decode()

    # Forced regeneration
    if "-force_vcfiles" in sys.argv or "-force_vcproj" in sys.argv:
        return src_digest

    # Regenerate if it doesn't exist
    if not os.path.exists(vcproj_path):
        return src_digest

    with open(vcproj_path, "r") as f:

        # Search the file for the previous digest
        dst_digest = None
        lines = f.readlines()
        for i in range(len(lines)):
            if 'Name="PiBDigest"' in lines[i] and i + 1 < len(lines):
                dst_digest = lines[i + 1].split('"')[1]

        # Regeneration required if it's not there
        if dst_digest == None:
            return src_digest

        # If they're equal, no need to return a new digest
        if src_digest == dst_digest:
            return None

        return src_digest


# Need: input files, configurations and args to run for configurations
def VCGenerateProjectFile(env, name, files, output, targets=None, configs=None, replacements = [ ], pibfile = "pibfile", include_search = [ ]):

    # Promote target to a list
    if targets != None and type(targets) != type([]):
        targets = [ targets ]
    
    # Exclude targets not mentioned on the command-line, if any
    if targets != None and len(env.BuildTargets):
        valid_targets = set(targets).intersection(env.BuildTargets)
        if len(valid_targets) == 0:
            return

    # Generate file paths
    vcproj_path = name + ".vcproj"
    vcproj_name = os.path.basename(name)
    vcproj_dir = os.path.dirname(vcproj_path)
    vcproj_guid = str(uuid.uuid1()).upper()

    # Remove the file if requested
    if "-remove_vcfiles" in sys.argv:
        if os.path.exists(vcproj_path):
            print("Deleting " + vcproj_path)
            os.remove(vcproj_path)
        return

    # Ensure the paths are normalised for stable hashing
    input_files = [ os.path.normcase(os.path.normpath(file)) for file in files]
    if targets != None:
        input_files += targets

    # Does the vcproj need to be regenerated?
    digest = DoesProjectNeedUpdating(vcproj_path, input_files)
    if digest == None:
        return vcproj_guid

    print("Generating VCProject file: " + vcproj_path)

    # Use default configs from the environment if none are specified
    if configs == None:
        configs = env.Configs

    pibcmd = None
    if pibfile != None:
        # Figure out the relative location of the pibfile
        pibfile = os.path.relpath(pibfile, vcproj_dir)
        pibfile_dir = os.path.dirname(pibfile)

        # Switch to the pibfile directory before launching the build
        pibcmd = "pib -pf " + os.path.basename(pibfile) + " "
        if pibfile_dir != "":
            pibcmd = "cd " + pibfile_dir + " &amp; " + pibcmd       # '&' in XML-speak

    # Construct target specification command-line option
    target_opt = ""
    if targets != None:
        for target in targets:
            target_opt += " -target " + target

    # Concatenate include search paths
    include_search_str = ""
    for include in include_search:
        include_search_str += include + ";"

    f = open(vcproj_path, "w")

    print('<?xml version="1.0" encoding="Windows-1252"?>', file=f)

    # Generate the header
    vcproj_header = ProjectHeader()
    header_xml = vcproj_header.replace("%NAME%", vcproj_name)
    header_xml = header_xml.replace("%GUID%", vcproj_guid)
    print(header_xml, file=f)

    # Generate each configuration
    print("\t<Configurations>", file=f)
    for name, config in env.Configs.items():

        xml = vcproj_config.replace("%CONFIG%", config.Name)

        xml = xml.replace("%OUTPUTDIR%", os.path.relpath(config.OutputPath, vcproj_dir))
        xml = xml.replace("%INTERDIR%", os.path.relpath(config.IntermediatePath, vcproj_dir))
        xml = xml.replace("%INCLUDESEARCH%", include_search_str)

        if pibcmd != None:
            xml = xml.replace("%BUILD%", pibcmd + "-config " + config.CmdLineArg + target_opt)
            xml = xml.replace("%REBUILD%", pibcmd + "rebuild " + "-config " + config.CmdLineArg + target_opt)
            xml = xml.replace("%CLEAN%", pibcmd + "clean " + "-config " + config.CmdLineArg + target_opt)
        else:
            xml = xml.replace("%BUILD%", "")
            xml = xml.replace("%REBUILD%", "")
            xml = xml.replace("%CLEAN%", "")

        # Specify the output executable for debugging
        if output != None:
            (output_path, output_ext) = output.GetPrimaryOutput(config)
            xml = xml.replace("%OUTPUT%", os.path.relpath(output_path + output_ext, vcproj_dir))
        else:
            xml = xml.replace("%OUTPUT%", "")

        print(xml, file=f)

    print("\t</Configurations>", file=f)
    print("\t<References>", file=f)
    print("\t</References>", file=f)

    # Create a hierarchical dictionary of folders and files
    folders = { }
    for file in files:

        # We need the path relative to the project file
        filename = os.path.relpath(file, vcproj_dir)
        filename = os.path.normpath(filename)
        
        # Separate the filename as seen in Visual Studio from the physical filename on disk
        # Perform any text replacements requested by the caller
        folder_filename = filename
        for r in replacements:
            folder_filename = folder_filename.replace(r[0], r[1])

        # Split the path into its component parts
        file_dir = os.path.dirname(folder_filename)
        dir_parts = []
        if file_dir != "":
            dir_parts = file_dir.split(os.sep)

        # Walk along each part creating any nodes looking for the final host directory
        host_dir = folders
        for part in dir_parts:
            if part not in host_dir:
                host_dir[part] = { }
            host_dir = host_dir[part]

        host_dir[filename] = None

    # Convert the dictionaries into sorted lists
    folders = CreateFolderLists(folders)

    print("\t<Files>", file=f)
    WriteProjectFiles(f, "\t\t", "", folders)
    print("\t</Files>", file=f)
    
    # Write the digest for detecting regeneration
    print("\t<Globals>", file=f)
    print("\t\t<Global", file=f)
    print('\t\t\tName="PiBDigest"', file=f)
    print('\t\t\tValue="' + digest + '"', file=f)
    print("\t\t/>", file=f)
    print("\t</Globals>", file=f)

    print("</VisualStudioProject>", file=f)
    f.close()


def DoesSolutionNeedUpdating(sln_path, projects):

    # Hash all the inputs
    # TODO: Output filename
    md5 = hashlib.md5()
    for name in projects:
        md5.update(bytes(name, "utf-8"))

    src_digest = md5.digest()
    src_digest = base64.urlsafe_b64encode(src_digest)
    src_digest = bytes(src_digest).decode()

    # Forced regeneration
    if "-force_vcfiles" in sys.argv or "-force_vcsln" in sys.argv:
        return src_digest

    # Regenerate if it doesn't exist
    if not os.path.exists(sln_path):
        return src_digest

    with open(sln_path, "r") as f:

        # Find the line with the metadata
        dst_digest = None
        lines = f.readlines()
        for line in lines:
            if line.startswith("\t\tPiBDigest = "):
                dst_digest = line.split(" = ")[1][:-1]
                break

        # Regeneration required if there's no comparison key
        if dst_digest == None:
            return src_digest

        # If they're equal, no need to return a new digest
        if src_digest == dst_digest:
            return None

        return src_digest


def ReadProjectGUID(vcproj_path):
    
    with open(vcproj_path, "r") as f:
        
        for line in f.readlines():
            
            line = line.strip()
            if line.startswith("ProjectGUID="):
                guid = line.split("=")[1][1:-1]
                return guid


def VCGenerateSolutionFile(env, name, add_dependencies, projects):

    sln_path = name + ".sln"

    # Remove the file if requested
    if "-remove_vcfiles" in sys.argv:
        if os.path.exists(sln_path):
            print("Deleting " + sln_path)
            os.remove(sln_path)
        return

    # Does the sln file need to be generated?
    digest = DoesSolutionNeedUpdating(sln_path, projects)
    if digest == None:
        return

    print("Generating Solution File: " + sln_path)

    f = open(sln_path, "w")

    sln_header = SolutionHeader()
    print(sln_header, file=f)

    # Write the project summary
    guids = { }
    prev_guid = None
    for name in projects:
        vcproj_path = os.path.normpath(name + ".vcproj")
        vcproj_name = os.path.basename(name)
        guids[name] = ReadProjectGUID(vcproj_path)

        # Need the vcproj path relative to the solution for Visual Studio
        vcproj_path = os.path.relpath(vcproj_path, os.path.dirname(sln_path))
        print('Project("{' + str(uuid.uuid1()).upper() + '}") = "' + vcproj_name + '", "' + vcproj_path + '", "' + guids[name] + '"', file=f)

        # Ensure the Solution build order matches the order in which projects were passed
        if add_dependencies and prev_guid != None:
            print("\tProjectSection(ProjectDependencies) = postProject", file=f)
            print("\t\t" + prev_guid + " = " + prev_guid, file=f)
            print("\tEndProjectSection", file=f)

        prev_guid = guids[name]
        print("EndProject", file=f)

    print("Global", file=f)
    print("\tGlobalSection(SolutionConfigurationPlatforms) = preSolution", file=f)

    # Write the configuration summary
    for config in env.Configs.values():
        print("\t\t" + config.Name + "|Win32 = " + config.Name + "|Win32", file=f)

    print("\tEndGlobalSection", file=f)
    print("\tGlobalSection(ProjectConfigurationPlatforms) = postSolution", file=f)

    # Write how each solution configs to each project config
    for name in projects:
        for config in env.Configs.values():
            config_name = config.Name + "|Win32"
            prefix = "\t\t" + guids[name] + "." + config_name
            print(prefix + ".ActiveCfg = " + config_name, file=f)
            print(prefix + ".Build.0 = " + config_name, file=f)

    print("\tEndGlobalSection", file=f)
    print("\tGlobalSection(SolutionProperties) = preSolution", file=f)
    print("\t\tHideSolutionNode = FALSE", file=f)
    print("\tEndGlobalSection", file=f)

    # Record the solution digest
    print("\tGlobalSection(ExtensibilityGlobals) = postSolution", file=f)
    print("\t\tPiBDigest = " + digest, file=f)
    print("\tEndGlobalSection", file=f)

    print("EndGlobal", file=f)

    f.close()
