# functions.py
# This file is part of labyrinth
#
# Copyright (C) 2006 - Don Scorgie
#
# labyrinth is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# labyrinth is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Labyrinth; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor,
# Boston, MA  02110-1301  USA
#

# This file defines various useful functions
# that can be accessed from anywhere :)

import sys
from os.path import *
import os


def get_save_dir ():
	''' Returns the path to the directory to save the maps to '''
	base = os.environ ['HOME']
	dirname = base+"/.gnome2/labyrinth/"
	if not os.access (dirname, os.W_OK):
		os.mkdir (dirname)
	return dirname

def parse_coords (string):
	if string == "None":
		return None
	local = string[1:string.find(',')]
	local_2 = string[string.find (',')+1:string.find(')')]
	coord = (float(local),	float(local_2))
	return coord

# Drawing functions

# These are thought outline styles.
# Currently, there is only 1 - STYLE_NORMAL, which is the slightly rounded corners
# - The normal thought type
STYLE_NORMAL = 0

def draw_thought_outline (context, ul, lr, am_root = False, am_primary = False, style=STYLE_NORMAL):
	if style == STYLE_NORMAL:
		draw_thought_classic (context, ul, lr, am_root, am_primary)
	else:
		print "Error: Unknown thought style: "+str(style)

# This is used to find the required margin from the (real) ul / lr coords to the edge of the
# box area.  Makes selection of thoughts less erratic
def margin_required (style = STYLE_NORMAL):
	if style == STYLE_NORMAL:
		return margin_thought_classic ()
	else:
		print "Error: Unknown thought margine style: "+str(style)

# Classic thought style drawing code
def margin_thought_classic ():
	return (5, 5, 5, 5)

def draw_thought_classic (context, ul, lr, am_root, am_primary):
	context.move_to (ul[0], ul[1]+5)
	context.line_to (ul[0], lr[1]-5)
	context.curve_to (ul[0], lr[1], ul[0], lr[1], ul[0]+5, lr[1])
	context.line_to (lr[0]-5, lr[1])
	context.curve_to (lr[0], lr[1], lr[0], lr[1], lr[0], lr[1]-5)
	context.line_to (lr[0], ul[1]+5)
	context.curve_to (lr[0], ul[1], lr[0], ul[1], lr[0]-5, ul[1])
	context.line_to (ul[0]+5, ul[1])
	context.curve_to (ul[0], ul[1], ul[0], ul[1], ul[0], ul[1]+5)
	if am_root:
		context.set_source_rgb (0.0,0.9,0.9)
	elif am_primary:
		context.set_source_rgb (1.0,0.5,0.5)
	else:
		context.set_source_rgb (1.0,1.0,1.0)
	context.fill_preserve ()
	context.set_source_rgb (0,0,0)
	context.stroke ()

# Export outline stuff
def export_thought_outline (context, ul, lr, am_root = False, am_primary = False, style=STYLE_NORMAL, move=(0,0)):
	real_ul = (ul[0]+move[0], ul[1]+move[1])
	real_lr = (lr[0]+move[0], lr[1]+move[1])
	if style == STYLE_NORMAL:
		draw_thought_classic (context, real_ul, real_lr, False, am_primary)
	else:
		print "Error: Unknown thought style: "+str(style)
