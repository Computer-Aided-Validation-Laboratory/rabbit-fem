// --------------------------------------------------------------------------------------
// Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
//
// Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
// Licensed under the GNU Lesser General Public License v2.1
// See LICENSE for details.
//
// Authors: scepticalrabbit (Lloyd Fletcher)
// --------------------------------------------------------------------------------------

//==============================================================================
// Gmsh 3D parametric plate with hole mesh
// author: Lloyd Fletcher (scepticalrabbit)
//==============================================================================
// Always set to OpenCASCADE - circles and boolean opts are much easier!
SetFactory("OpenCASCADE");

// Allows gmsh to print to terminal in vscode - easier debugging
General.Terminal = 1;

// View options - not required when
Geometry.PointLabels = 0;
Geometry.CurveLabels = 0;
Geometry.SurfaceLabels = 1;
Geometry.VolumeLabels = 0;

//------------------------------------------------------------------------------
// Variables

// Geometric variables
plate_width = 25.0;
plate_height = 35.0;
plate_diff = plate_height-plate_width;
plate_thick = 1.0;

hole_rad = plate_width/8;
hole_loc_x = 0.0;
hole_loc_y = plate_height/2;
hole_circ = 2*Pi*hole_rad;

// Mesh variables
If(!Exists(MR))
    MR = 2;
EndIf
If(!Exists(bias_factor))
    bias_factor = 1.25;
EndIf
file_name = "mesh3d_holeplate.msh"; 

elem_order = 2;
second_ord_incomp = 1;

plate_thick_layers = 2;
hole_sect_nodes = 2*Floor((5*MR - 1)/2)+1; // Must be odd
plate_rad_nodes = 2*Floor((5*MR - 1)/2)+1;
plate_diff_nodes = 2*Floor((4*MR - 1)/2); // numbers of nodes along the rectangular extension

plate_edge_nodes = Floor((hole_sect_nodes-1)/2)+1;
elem_size = hole_circ/(4*(hole_sect_nodes-1));

tol = elem_size; // Used for bounding box selection tolerance
tol_thick = plate_thick/4;

//------------------------------------------------------------------------------
// Geometry Definition

// Split plate into eight pieces with a square around the hole to allow spider
// web meshing around the hole
s1 = news;
Rectangle(s1) = {-plate_width/2,0.0,0.0,
                plate_width/2,plate_diff/2};
s2 = news;
Rectangle(s2) = {0.0,0.0,0.0,
                plate_width/2,plate_diff/2};

s3 = news;
Rectangle(s3) = {-plate_width/2,plate_diff/2,0.0,
                plate_width/2,plate_width/2};
s4 = news;
Rectangle(s4) = {0.0,plate_diff/2,0.0,
                plate_width/2,plate_width/2};

s5 = news;
Rectangle(s5) = {-plate_width/2,plate_width/2+plate_diff/2,0.0,
                plate_width/2,plate_width/2};
s6 = news;
Rectangle(s6) = {0.0,plate_width/2+plate_diff/2,0.0,
                plate_width/2,plate_width/2};

s7 = news;
Rectangle(s7) = {-plate_width/2,plate_height-plate_diff/2,0.0,
                plate_width/2,plate_diff/2};
s8 = news;
Rectangle(s8) = {0.0,plate_height-plate_diff/2,0.0,
                plate_width/2,plate_diff/2};

// Merge coincicent edges of the four overlapping squares
BooleanFragments{ Surface{s1}; Delete; }
                { Surface{s2,s3,s4,s5,s6,s7,s8}; Delete; }

// Create the hole surface
c2 = newc; Circle(c2) = {hole_loc_x,hole_loc_y,0.0,hole_rad};
cl2 = newcl; Curve Loop(cl2) = {c2};
s9 = news; Plane Surface(s9) = {cl2};
// Bore out the hole from the quarters of the plate
BooleanDifference{ Surface{s3,s4,s5,s6}; Delete; }{ Surface{s9}; Delete; }

//------------------------------------------------------------------------------
// Transfinite meshing (line element sizes and mapped meshing)
Transfinite Curve{31,24} = plate_rad_nodes Using Progression bias_factor;
Transfinite Curve{26,28} = plate_rad_nodes Using Progression 1/bias_factor;
Transfinite Curve{1,5,3,7,23,29,30,34,14,17,19,22} = plate_edge_nodes;
Transfinite Curve{32,33,25,27} = hole_sect_nodes;
Transfinite Curve{4,2,6,20,18,21} = plate_diff_nodes;

// NOTE: recombine surface turns default triangles into quads

Transfinite Surface{s1} = {1,2,3,4};
Recombine Surface{s1};
Transfinite Surface{s2} = {2,5,6,3};
Recombine Surface{s2};

Transfinite Surface{s3} = {17,18,3,16};
Recombine Surface{s3};
Transfinite Surface{s4} = {18,19,20,3};
Recombine Surface{s4};
Transfinite Surface{s5} = {17,21,10,16};
Recombine Surface{s5};
Transfinite Surface{s6} = {19,21,10,20};
Recombine Surface{s6};

Transfinite Surface{s7} = {11,10,13,14};
Recombine Surface{s7};
Transfinite Surface{s8} = {10,12,15,13};
Recombine Surface{s8};

Extrude{0.0,0.0,plate_thick}{
    Surface{:}; Layers{plate_thick_layers}; Recombine;
}

//------------------------------------------------------------------------------
// Physical lines and surfaces for export/BCs
Physical Volume("plate-vol") = {Volume{:}};

ps1() = Surface In BoundingBox{
    -plate_width/2-tol,plate_height-tol,0.0-tol,
    plate_width/2+tol,plate_height+tol,plate_thick+tol};
Physical Surface("bc-top") = {ps1()};

ps2() = Surface In BoundingBox{
    -plate_width/2-tol,0.0-tol,0.0-tol,
    plate_width/2+tol,0.0+tol,plate_thick+tol};
Physical Surface("bc-bot") = {ps2()};

// Mid-points on top and bottom boundaries for pinning X/Z displacement
p_bot_1() = Point In BoundingBox{-tol, -tol, -tol, tol, tol, tol};
p_bot_2() = Point In BoundingBox{-tol, -tol, plate_thick-tol, tol, tol, plate_thick+tol};
Physical Point("bc-bot-point-back") = {p_bot_1(0)};
Physical Point("bc-bot-point-front") = {p_bot_2(0)};

p_top_1() = Point In BoundingBox{-tol, plate_height-tol, -tol, tol, plate_height+tol, tol};
p_top_2() = Point In BoundingBox{-tol, plate_height-tol, plate_thick-tol, tol, plate_height+tol, plate_thick+tol};
Physical Point("bc-top-mid") = {p_top_1(0), p_top_2(0)};

ps3() = Surface In BoundingBox{
    -plate_width/2-tol,0.0-tol,plate_thick-tol_thick,
    plate_width/2+tol,plate_height+tol,plate_thick+tol_thick};
Physical Surface("plate-surf-vis-front") = {ps3()};

ps4() = Surface In BoundingBox{
    -plate_width/2-tol,0.0-tol,0.0-tol_thick,
    plate_width/2+tol,plate_height+tol,0.0+tol_thick};
Physical Surface("plate-surf-vis-back") = {ps4()};

//------------------------------------------------------------------------------
// Global meshing
num_threads = 4;

Mesh.Algorithm = 6;
Mesh.Algorithm3D = 10;

General.NumThreads = num_threads;
Mesh.MaxNumThreads1D = num_threads;
Mesh.MaxNumThreads2D = num_threads;
Mesh.MaxNumThreads3D = num_threads;

Mesh.ElementOrder = elem_order;
Mesh.SecondOrderIncomplete = second_ord_incomp;

Mesh 3;

//------------------------------------------------------------------------------
// Save and exit
Save Str(file_name);
//Exit;
