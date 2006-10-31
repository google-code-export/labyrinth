#! /usr/bin/env python
# MMapArea.py
# This file is part of Labyrinth
#
# Copyright (C) 2006 - Don Scorgie <DonScorgie@Blueyonder.co.uk>
#
# Labyrinth is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Labyrinth is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Labyrinth; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor,
# Boston, MA  02110-1301  USA
#

import time
import gtk
import pango
import gobject
import gettext
_ = gettext.gettext

import xml.dom.minidom as dom

import Links
import TextThought
import ImageThought
import DrawingThought

MODE_EDITING = 0
MODE_IMAGE = 1
MODE_DRAW = 2
# Until all references of MODE_MOVING are removed...
MODE_MOVING = 999

TYPE_TEXT = 0
TYPE_IMAGE = 1
TYPE_DRAW = 2

# TODO: Need to expand to support popup menus
MENU_EMPTY_SPACE = 0

# Note: This is (atm) very broken.  It will allow you to create new canvases, but not
# create new thoughts or load existing maps.
# To get it working either fix the TODO list at the bottom of the class, implement the
# necessary features within all the thought types.  If you do, please send a patch ;)
# OR: Change this class to MMapAreaNew and MMapAreaOld to MMapArea

class MMapArea (gtk.DrawingArea):
	'''A MindMapArea Widget.  A blank canvas with a collection of child thoughts.\
	   It is responsible for processing signals and such from the whole area and \
	   passing these on to the correct child.  It also informs things when to draw'''

	__gsignals__ = dict (title_changed		= (gobject.SIGNAL_RUN_FIRST,
											   gobject.TYPE_NONE,
											   (gobject.TYPE_STRING, )),
						 doc_save			= (gobject.SIGNAL_RUN_FIRST,
											   gobject.TYPE_NONE,
											   (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
						 doc_delete         = (gobject.SIGNAL_RUN_FIRST,
						 					   gobject.TYPE_NONE,
						 					   ()),
						 change_mode        = (gobject.SIGNAL_RUN_LAST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_INT, )),
						 change_buffer      = (gobject.SIGNAL_RUN_LAST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_OBJECT, )),
						 text_selection_changed  = (gobject.SIGNAL_RUN_FIRST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_INT, gobject.TYPE_INT, gobject.TYPE_STRING)))

	def __init__(self):
		super (MMapArea, self).__init__()

		self.thoughts = []
		self.links = []
		self.selected = []
		self.num_selected = 0
		self.primary = None
		self.editing = None
		self.pango_context = self.create_pango_context()

		self.unending_link = None
		self.nthoughts = 0

		impl = dom.getDOMImplementation()
		self.save = impl.createDocument("http://www.donscorgie.blueyonder.co.uk/labns", "MMap", None)
		self.element = self.save.documentElement
		self.im_context = gtk.IMMulticontext ()

		self.mode = MODE_EDITING

		self.connect ("expose_event", self.expose)
		self.connect ("button_release_event", self.button_release)
		self.connect ("button_press_event", self.button_down)
		self.connect ("motion_notify_event", self.motion)
		self.connect ("key_press_event", self.key_press)
		self.connect ("key_release_event", self.key_release)
		self.commit_handler = None
		self.title_change_handler = None

		self.set_events (gtk.gdk.KEY_PRESS_MASK |
						 gtk.gdk.KEY_RELEASE_MASK |
						 gtk.gdk.BUTTON_PRESS_MASK |
						 gtk.gdk.BUTTON_RELEASE_MASK |
						 gtk.gdk.POINTER_MOTION_MASK
						)

		self.set_flags (gtk.CAN_FOCUS)


	def button_down (self, widget, event):
		ret = False
		obj = self.find_object_at (event.get_coords())

		if obj:
			ret = obj.process_button_down (event, self.mode)
		elif event.button == 3:
			ret = self.create_popup_menu (event.get_coords (), MENU_EMPTY_SPACE)
		return ret

	def button_release (self, widget, event):
		ret = False
		obj = self.find_object_at (event.get_coords ())

		if obj:
			ret = obj.process_button_release (event, self.unending_link, self.mode)
		elif self.unending_link or event.button == 1:
			thought = self.create_new_thought (event.get_coords ())
			if not self.primary:
				self.make_primary (thought)
			for x in self.selected:
				self.create_link (x, None, thought)
			self.select_thought (thought, None)
			self.begin_editing (thought)
		self.invalidate ()
		return ret

	def key_press (self, widget, event):
		if not self.im_context.filter_keypress (event):
			if len(self.selected) != 1 or not self.selected[0].process_key_press (event, self.mode):
				return self.global_key_handler (event)
		return True

	def key_release (self, widget, event):
		self.im_context.filter_keypress (event)
		return True

	def motion (self, widget, event):
		if self.unending_link:
			self.unending_link.set_end (event.get_coords())
			self.invalidate ()
			return True

		obj = self.find_object_at (event.get_coords())
		if obj:
			obj.handle_motion (event, self.mode)
		elif self.mode == MODE_IMAGE or self.mode == MODE_DRAW:
			self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.CROSSHAIR))
		else:
			self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.LEFT_PTR))

	def find_object_at (self, coords):
		for x in self.thoughts:
			if x.includes (coords, self.mode):
				return x
		for x in self.links:
			if x.includes (coords, self.mode):
				return x
		return None

	def set_mode (self, mode):
		self.old_mode = self.mode
		self.mode = mode
		self.finish_editing ()

		if mode == MODE_IMAGE or mode == MODE_DRAW:
			self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.CROSSHAIR))
		else:
			self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.LEFT_PTR))

		self.mode = mode
		self.invalidate ()

	def title_changed_cb (self, widget, new_title):
		self.emit ("title_changed", new_title)

	def make_primary (self, thought):
		if self.primary:
			print "Warning: Already have a primary root"
			if self.title_change_handler:
				self.primary.disconnect (self.title_change_handler)
		self.title_change_handler = thought.connect ("title_changed", self.title_changed_cb)
		self.primary = thought
		thought.make_primary ()

	def select_thought (self, thought, modifiers):
		if self.commit_handler:
			self.im_context.disconnect (self.commit_handler)
			self.commit_handler = None
		if self.editing:
			self.finish_editing ()
		self.thoughts.remove (thought)
		self.thoughts.insert(0,thought)

		if modifiers and modifiers & gtk.gdk.CONTROL_MASK:
			self.selected.append (thought)
		elif modifiers and modifiers & gtk.gdk.SHIFT_MASK:
			# TODO: This should really be different somehow
			self.selected.append (thought)
		else:
			for x in self.selected:
				x.unselect ()
			self.selected = [thought]
		thought.select ()
		if len(self.selected) == 1:
			self.emit ("change_buffer", thought.extended_buffer)
			self.commit_handler = self.im_context.connect ("commit", thought.commit_text, self.mode)
		else:
			self.emit ("change_buffer", None)

	def begin_editing (self, thought):
		if self.selected.count (thought) != 1 or len (self.selected) != 1:
			return
		if self.editing:
			self.finish_editing ()
		self.editing = thought
		thought.begin_editing ()

	def create_link (self, thought, thought_coords = None, child = None, child_coords = None):
		if child:
			for x in self.links:
				if x.connects (thought, child):
					if not x.change_strength (thought, child):
						self.delete_link (x)
					return
			link = Links.Link (self.save, parent = thought, child = child)
			element = link.get_save_element ()
			self.element.appendChild (element)
			self.links.append (link)
		else:
			if self.unending_link:
				del self.unending_link
			self.unending_link = Links.Link (self.save, parent = thought, start_coords = thought_coords,
											 end_coords = child_coords)

	def set_mouse_cursor_cb (self, thought, cursor_type):
		self.window.set_cursor (gtk.gdk.Cursor (cursor_type))

	def update_links_cb (self, thought):
		for x in self.links:
			if x.uses (thought):
				x.find_ends ()

	def claim_unending_link (self, thought):
		if not self.unending_link:
			return
		for x in self.links:
			if x.connects (self.unending_link.parent, thought):
				x.change_strength (self.unending_link.parent, thought)
				del self.unending_link
				self.unending_link = None
				return
		self.unending_link.set_child (thought)
		self.links.append (self.unending_link)
		self.unending_link = None

	def create_popup_menu (self, thought, coords, menu_type):
		# TODO: FIXME
		print "Popup menu requested"
		return

	def finish_editing (self, thought = None):
		if not self.editing or (thought and thought != self.editing):
			return
		self.editing.finish_editing ()
		self.editing = None

	def update_view (self, thought):
		self.invalidate ()

	def invalidate (self):
		'''Helper function to invalidate the entire screen, forcing a redraw'''
		alloc = self.get_allocation ()
		rect = gtk.gdk.Rectangle (0, 0, alloc.width, alloc.height)
		self.window.invalidate_rect (rect, True)

	def expose (self, widget, event):
		'''Expose event.  Calls the draw function'''
		context = self.window.cairo_create ()
		self.draw (event, context)
		return False

	def draw (self, event, context):
		'''Draw the map and all the associated thoughts'''
		context.rectangle (event.area.x, event.area.y,
						   event.area.width, event.area.height)
		context.clip ()
		context.set_source_rgb (1.0,1.0,1.0)
		context.move_to (0,0)
		context.paint ()
		context.set_source_rgb (0.0,0.0,0.0)
		for l in self.links:
			l.draw (context)
		if self.unending_link:
			self.unending_link.draw (context)
		for t in self.thoughts:
			t.draw (context)

	def create_new_thought (self, coords, thought_type = None, loading = False):
		if self.editing:
			self.editing.finish_editing ()

		if thought_type:
			type = thought_type
		else:
			type = self.mode

		if type == TYPE_TEXT:
			thought = TextThought.TextThought (coords, self.pango_context, self.nthoughts, self.save, loading)
		elif type == TYPE_IMAGE:
			thought = ImageThought.ImageThought (coords, self.pango_context, self.nthoughts, self.save, loading)
		elif type == TYPE_DRAWING:
			thought = DrawingThought.DrawingThought (coords, self.pango_context, self.nthoughts, self.save, loading)
		if not thought.okay ():
			print "Something very, very bad happened"
		elif type == TYPE_IMAGE:
			self.emit ("change_mode", self.old_mode)

		self.nthoughts += 1
		element = thought.element
		self.element.appendChild (thought.element)
		thought.connect ("select_thought", self.select_thought)
		thought.connect ("begin_editing", self.begin_editing)
		thought.connect ("popup_requested", self.create_popup_menu)
		thought.connect ("create_link", self.create_link)
		thought.connect ("claim_unending_link", self.claim_unending_link)
		thought.connect ("update_view", self.update_view)
		thought.connect ("finish_editing", self.finish_editing)
		thought.connect ("delete_thought", self.delete_thought)
		thought.connect ("text_selection_changed", self.text_selection_cb)
		thought.connect ("change_mouse_cursor", self.set_mouse_cursor_cb)
		thought.connect ("update_links", self.update_links_cb)
		self.thoughts.insert (0, thought)

		return thought

	def delete_thought (self, thought):
		self.element.removeChild (thought.element)
		thought.element.unlink ()
		self.thoughts.remove (thought)
		try:
			self.selected.remove (thought)
		except:
			pass
		if self.primary == thought:
			thought.disconnect (self.title_change_handler)
			self.title_change_handler = None
			self.primary = None
			if self.thoughts:
				self.make_primary (self.thoughts[0])
		rem_links = []
		for l in self.links:
			if l.uses (thought):
				rem_links.append (l)
		for l in rem_links:
			self.delete_link (l)
		del thought
		return True

	def delete_selected_thoughts (self):
		for t in self.selected:
			self.delete_thought (t)

	def delete_link (self, link):
		self.element.removeChild (link.element)
		link.element.unlink ()
		self.links.remove (link)

	def global_key_handler (self, event):
		# Use a throw-away dictionary for keysym lookup.
		# Idea from: http://simon.incutio.com/archive/2004/05/07/switch
		# Dunno why.  Just trying things out
		try:
			{ gtk.keysyms.Delete: self.delete_selected_thoughts,
			  gtk.keysyms.BackSpace: self.delete_selected_thoughts}[event.keysym]()
		except:
			return False
		self.invalidate ()
		return True

	def load_thought (self, node, type):
		thought = create_new_thought (None, type)
		thought.load (node)

	def load_link (self, node):
		link = Links.Link (self.save)
		link.load (node)
		self.links.append (link)

	def load_thyself (self, top_element, doc):
		for node in top_element.childNodes:
			if node.nodeName == "thought":
				self.load_thought (node, TYPE_TEXT, loading = True)
			elif node.nodeName == "image_thought":
				self.load_thought (node, TYPE_IMAGE, loading = True)
			elif node.nodeName == "drawing_thought":
				self.load_thought (node, TYPE_DRAWING, loading = True)
			elif node.nodeName == "link":
				self.load_link (node)
			else:
				print "Warning: Unknown element type.  Ignoring: "+node.nodeName

		self.finish_loading ()

	def finish_loading (self):
		# Possible TODO: This all assumes we've been given a proper,
		# consistant file.  It should fallback nicely, but...
		# First, find the primary root:
		for t in self.thoughts:
			if t.am_primary:
				self.make_primary (t)
			if t.am_selected:
				self.select_thought (t)
			if t.editing:
				self.begin_editing (t)
		del_links = []
		for l in self.links:
			if l.parent_number == -1 and l.child_number == -1:
				del_links.append (l)
				continue
			parent = child = None
			for t in self.thoughts:
				if t.identity == l.parent_number:
					parent = t
				elif t.identity == l.child_number:
					child = t
				if parent and child:
					break
			l.set_parent_child (parent, child)
			if not l.parent or not l.child:
				del_links.append (l)
		for l in del_links:
			self.delete_link (l)

	def save_thyself (self):
		for t in self.thoughts:
			t.update_save ()
		for l in self.links:
			l.update_save ()
		if len(self.thoughts) > 0:
			self.emit ("doc_save", self.save, self.element)
		else:
			self.emit ("doc_delete")

	def text_selection_cb (self, thought, start, end, text):
		self.emit ("text_selection_changed", start, end, text)

	def copy_clipboard (self, clip):
		if len (self.selected) != 1:
			return
		self.selected[0].copy_text (clip)


	def cut_clipboard (self, clip):
		if len (self.selected) != 1:
			return
		self.selected[0].cut_text (clip)


	def paste_clipboard (self, clip):
		if len (self.selected) != 1:
			return
		self.selected[0].paste_text (clip)

	def export (self, context, width, height, native):
		context.rectangle (0, 0, width, height)
		context.clip ()
		context.set_source_rgb (1.0,1.0,1.0)
		context.move_to (0,0)
		context.paint ()
		context.set_source_rgb (0.0,0.0,0.0)
		if not native:
			move_x = self.move_x
			move_y = self.move_y
		else:
			move_x = 0
			move_y = 0
		for l in self.links:
			l.export (context, move_x, move_y)
		for t in self.thoughts:
			t.export (context, move_x, move_y)

	def get_max_area (self):
		minx = 999
		maxx = -999
		miny = 999
		maxy = -999

		for t in self.thoughts:
			mx,my,mmx,mmy = t.get_max_area ()
			if mx < minx:
				minx = mx
			if my < miny:
				miny = my
			if mmx > maxx:
				maxx = mmx
			if mmy > maxy:
				maxy = mmy
		# Add a 10px border around all
		self.move_x = 10-minx
		self.move_y = 10-miny
		maxx = maxx-minx+20
		maxy = maxy-miny+20
		return (maxx,maxy)

	def get_selection_bounds (self):
		if len (self.selected) == 1:
			return self.selected[0].index, self.selected[0].end_index
		else:
			return None, None


class MMapAreaOld (gtk.DrawingArea):
	'''A MindMapArea Widget.  A blank canvas with a collection of child thoughts.\
	   It is responsible for processing signals and such from the whole area and \
	   passing these on to the correct child.  It also informs things when to draw'''

	__gsignals__ = dict (single_click_event = (gobject.SIGNAL_RUN_FIRST,
											   gobject.TYPE_NONE,
											   (gobject.TYPE_PYOBJECT, gobject.TYPE_INT, gobject.TYPE_INT)),
						 double_click_event = (gobject.SIGNAL_RUN_FIRST,
											   gobject.TYPE_NONE,
											   (gobject.TYPE_PYOBJECT, gobject.TYPE_INT, gobject.TYPE_INT)),
						 title_changed		= (gobject.SIGNAL_RUN_FIRST,
											   gobject.TYPE_NONE,
											   (gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)),
						 doc_save			= (gobject.SIGNAL_RUN_FIRST,
											   gobject.TYPE_NONE,
											   (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)),
						 doc_delete         = (gobject.SIGNAL_RUN_FIRST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_PYOBJECT, )),
						 change_mode        = (gobject.SIGNAL_RUN_LAST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_INT, )),
						 change_buffer      = (gobject.SIGNAL_RUN_LAST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_OBJECT, )),
						 text_selection_changed = (gobject.SIGNAL_RUN_FIRST,
						 					   gobject.TYPE_NONE,
						 					   (gobject.TYPE_INT, gobject.TYPE_INT, gobject.TYPE_STRING)))

	def __init__(self):
		super (MMapArea, self).__init__()

		self.thoughts = []
		self.links = []
		self.selected_thoughts = []
		self.num_selected = 0
		self.primary_thought = None
		self.current_root = None
		self.connect ("expose_event", self.expose)
		self.connect ("button_release_event", self.button_release)
		self.connect ("button_press_event", self.button_down)
		self.connect ("motion_notify_event", self.motion)
		self.connect ("key_press_event", self.key_press)
		self.connect ("key_release_event", self.key_release)
		self.connect ("single_click_event", self.single_click)
		self.connect ("double_click_event", self.double_click)

		self.set_events (gtk.gdk.KEY_PRESS_MASK |
						 gtk.gdk.BUTTON_PRESS_MASK |
						 gtk.gdk.BUTTON_RELEASE_MASK |
						 gtk.gdk.POINTER_MOTION_MASK
						)
		self.set_flags (gtk.CAN_FOCUS)
		self.pango_context = self.create_pango_context()
		self.mode = MODE_EDITING
		self.watching_movement = False
		self.release_time = None

		self.unended_link = None
		self.nthoughts = 0
		self.b_down = False

		impl = dom.getDOMImplementation()
		self.save = impl.createDocument("http://www.donscorgie.blueyonder.co.uk/labns", "MMap", None)
		self.element = self.save.documentElement
		self.im_context = gtk.IMMulticontext ()

		self.time_elapsed = 0.0

# Signal Handlers for the Map Class

	def button_down (self, widget, event):
		self.b_down = True

		thought = self.find_thought_at (event.get_coords (), event.state)

		if thought:
			if thought != self.editing:
				self.finish_editing ()
			#for t in self.selected_thoughts:
			#	if t != thought:
			#		self.finish_editing (t)
			self.make_current_root (thought)
			self.select_thought (thought)
			self.watching_movement = True
		self.emit ("text_selection_changed", 0, 0, None)
		self.invalidate ()
		return False

	def button_release (self, widget, event):
		self.b_down = False
		self.watching_movement = False
		if len (self.selected_thoughts) > 0:
			self.selected_thoughts[0].finish_motion ()
			self.update_links (self.selected_thoughts[0])

		self.prev_release_time = self.release_time
		self.release_time = event.get_time ()

		if self.prev_release_time and (self.release_time - self.prev_release_time) < 700:
			self.release_time = None
			self.emit ("double_click_event", event.get_coords (), event.state, event.button)
		else:
			self.emit ("single_click_event", event.get_coords (), event.state, event.button)
		self.invalidate ()
		return False

	def motion (self, widget, event):
		if not self.watching_movement:
			return False

		if self.mode == MODE_EDITING or self.mode == MODE_DRAW:
			self.handle_movement (event.get_coords ())
			self.invalidate ()
			return False

		for s in self.selected_thoughts:
			s.handle_movement (event.get_coords ())
			self.update_links (s)

		self.invalidate ()
		return False

	def key_press (self, widget, event):
		if self.mode == MODE_EDITING:
			if self.num_selected > 1 or self.num_selected == 0:
				return False
			self.edit_thought (self.selected_thoughts[0])
			if self.im_context.filter_keypress (event):
				return True
			ret = self.selected_thoughts[0].handle_key (event.string, event.keyval, event.state)
			index = self.selected_thoughts[0].index
			end = self.selected_thoughts[0].end_index
			if end > index:
				text = self.selected_thoughts[0].text[index:end]
			elif end < index:
				text = self.selected_thoughts[0].text[end:index]
			else:
				text = ""
			self.emit ('text_selection_changed', index, end, text)
		else:
			ret = self.handle_key_global (event.keyval)
			self.emit ('text_selection_changed', 0, 0, "")
		self.invalidate ()
		return ret

	def key_release (self, widget, event):
		self.im_context.filter_keypress (event)
		return True

	def expose (self, widget, event):
		'''Expose event.  Calls the draw function'''
		context = self.window.cairo_create ()
		self.draw (event, context)
		return False

	def single_click (self, widget, coords, state, button):
		# For now, ignore any other buttons
		if button != 1:
			return
		thought = self.find_thought_at (coords, state)

		#We may have a dangling link.  Need to destroy it now
		self.unended_link = None

		if thought:
			if self.num_selected == 1 and thought != self.selected_thoughts[0]:
				self.link_thoughts (self.selected_thoughts[0], thought)
			elif self.num_selected == 1:
				self.make_current_root (thought)
		else:
			if self.mode == MODE_EDITING:
				self.create_new_thought (coords)
			elif self.mode == MODE_IMAGE:
				self.create_image (coords)
			elif self.mode == MODE_DRAW:
			    self.create_drawing (coords)
			else:
				self.unselect_all ()
		self.invalidate ()
		return

	def double_click (self, widget, coords, state, button):
		if button != 1:
			return

		thought = self.find_thought_at (coords, state)

		if self.mode == MODE_EDITING:
			if thought:
				self.edit_thought (thought)
			else:
				self.create_new_thought (coords)

		self.invalidate ()
		return

	def title_changed_cb (self, widget, new_title, obj):
		self.emit ("title_changed", new_title, obj)

# Other functions

	def draw (self, event, context):
		'''Draw the map and all the associated thoughts'''
		context.rectangle (event.area.x, event.area.y,
						   event.area.width, event.area.height)
		context.clip ()
		context.set_source_rgb (1.0,1.0,1.0)
		context.move_to (0,0)
		context.paint ()
		context.set_source_rgb (0.0,0.0,0.0)
		for l in self.links:
			l.draw (context)
		if self.unended_link:
			self.unended_link.draw (context)
		for t in self.thoughts:
			t.draw (context)

	def invalidate (self, ignore = None, urgent = True):
		'''Helper function to invalidate the entire screen, forcing a redraw'''
		ntime = time.time ()
		if ntime - self.time_elapsed > 0.025 or urgent:
			alloc = self.get_allocation ()
			rect = gtk.gdk.Rectangle (0, 0, alloc.width, alloc.height)
			self.window.invalidate_rect (rect, True)
			self.time_elapsed = ntime

	def find_thought_at (self, coords, state):
		'''Checks the given coords and sees if there are any thoughts there'''
		if self.mode == MODE_EDITING and self.b_down:
			allow_resize = True
		else:
			allow_resize = False
		for thought in self.thoughts:
			if thought.includes (coords, allow_resize, state):
				return thought
		return None

	def create_new_thought (self, coords):
		for t in self.selected_thoughts:
			self.finish_editing (t)

		elem = self.save.createElement ("thought")
		text_element = self.save.createTextNode ("GOOBAH")
		extended_elem = self.save.createElement ("Extended")
		extended_element = self.save.createTextNode ("Extended")
		elem.appendChild (text_element)
		elem.appendChild (extended_elem)
		extended_elem.appendChild (extended_element)
		self.element.appendChild (elem)
		thought = TextThought.TextThought (coords, self.pango_context, self.nthoughts, elem, text_element, \
										   extended_element = extended_element)
		self.edit_thought (thought)
		self.nthoughts += 1
		if self.current_root:
			self.link_thoughts (self.current_root, thought)
		else:
			self.make_current_root (thought)

		if not self.primary_thought:
			self.make_primary_root (thought)
		thought.connect ("delete_thought", self.delete_thought)
		thought.connect ("update_view", self.invalidate)
		self.select_thought (thought)
		self.edit_thought (thought)
		self.thoughts.append (thought)
		self.invalidate ()


	def load_thought (self, node):
		elem = self.save.createElement ("thought")
		text_element = self.save.createTextNode ("")
		extended_elem = self.save.createElement ("Extended")
		extended_element = self.save.createTextNode ("Extended")
		elem.appendChild (text_element)
		elem.appendChild (extended_elem)
		extended_elem.appendChild (extended_element)
		self.element.appendChild (elem)
		thought = TextThought.TextThought (element = elem, text_element = text_element, pango=self.pango_context, load=node, extended_element = extended_element)
		if thought.editing:
			thought.editing = False
			self.edit_thought (thought)
		self.thoughts.append (thought)
		if thought.identity >= self.nthoughts:
			self.nthoughts = thought.identity+1
		thought.connect ("update_view", self.invalidate)
		thought.connect ("delete_thought", self.delete_thought)

	def load_link (self, node):
		link_elem = self.save.createElement ("link")
		self.element.appendChild (link_elem)
		link = Links.Link (element = link_elem, load=node)
		self.links.append (link)

	def finish_loading (self):
		# First, find the primary root:
		for t in self.thoughts:
			if t.am_primary:
				t.connect ("title_changed", self.title_changed_cb)
				self.primary_thought = t
			if t.am_root:
				self.select_thought (t)
				self.current_root = t
			if t.editing:
				self.select_thought (t)
				#self.selected_thoughts = [t]
				self.num_selected = 1
		del_links = []
		for l in self.links:
			if l.parent_number == -1 and l.child_number == -1:
				del_links.append (l)
				continue
			parent = child = None
			for t in self.thoughts:
				if t.identity == l.parent_number:
					parent = t
				elif t.identity == l.child_number:
					child = t
				if parent and child:
					break
			l.set_ends (parent, child)
			if not l.parent or not l.child:
				del_links.append (l)
		for l in del_links:
			self.delete_link (l)

	def handle_movement (self, coords):
		# We can only be called (for now) if a node is selected.  Plan accordingly.

		if self.selected_thoughts[0].want_movement ():
			handled = self.selected_thoughts[0].handle_movement (coords, False, self.mode == MODE_EDITING)
			index = self.selected_thoughts[0].index
			end = self.selected_thoughts[0].end_index
			if end > index:
				text = self.selected_thoughts[0].text[index:end]
			elif end < index:
				text = self.selected_thoughts[0].text[end:index]
			else:
				text = ""
			self.emit ('text_selection_changed', index, end, text)
			self.update_links (self.selected_thoughts[0])
			self.invalidate ()
			if handled:
				return
		if not self.unended_link:
			self.unended_link = Links.Link (parent = self.selected_thoughts[0], from_coords = coords)
		self.unended_link.set_new_end (coords)
		self.invalidate ()
		return

	def handle_key_global (self, keysym):
		# Use a throw-away dictionary for keysym lookup.
		# Idea from: http://simon.incutio.com/archive/2004/05/07/switch
		# Dunno why.  Just trying things out
		try:
			{ gtk.keysyms.Delete: self.delete_selected_nodes,
			  gtk.keysyms.BackSpace: self.delete_selected_nodes}[keysym]()
		except:
			return False
		self.invalidate ()
		return True

	def link_thoughts (self, parent, child):
		link = None
		for l in self.links:
			if l.connects (parent, child):
				link = l
				break
		if not link:
			link_elem = self.save.createElement ("link")
			self.element.appendChild (link_elem)
			link = Links.Link (parent, child, link_elem)
			link.update ()
			self.links.append (link)
		else:
			do_del = l.mod_strength (parent, child)
			if do_del:
				self.delete_link (l)
		self.invalidate ()

	def edit_thought (self, thought):
		if not thought.editing:
			self.select_thought (thought)
			thought.begin_editing (self.im_context)
			self.update_links (thought)

	def make_current_root (self, thought):
		if self.current_root and self.current_root != thought:
			self.current_root.finish_active_root ()
		self.current_root = thought
		if thought:
			thought.become_active_root ()
		self.invalidate ()

	def unselect_all (self):
		self.num_selected = 0
		self.selected_thoughts = []
		self.invalidate ()

	def delete_selected_nodes (self):
		for t in self.selected_thoughts:
			self.delete_thought (t)
		self.invalidate ()

	def make_primary_root (self, thought):
		thought.connect ("title_changed", self.title_changed_cb)
		thought.become_primary_thought ()
		self.primary_thought = thought
		self.current_root = self.primary_thought
		self.current_root.become_active_root ()
		self.emit ("title_changed", thought.text, thought)

	def set_mode (self, mode, invalidate = True):
		#if self.mode == MODE_IMAGE:
		#	self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.LEFT_PTR))
		if mode == MODE_MOVING:
			for s in self.selected_thoughts:
				self.finish_editing (s)
		if (mode == MODE_IMAGE or mode == MODE_DRAW) and invalidate:
		#	self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.CROSSHAIR))
			self.old_mode = self.mode
		self.mode = mode
		if invalidate:
			self.invalidate ()

	def save_thyself (self):
		for t in self.thoughts:
			t.update_save ()
		for l in self.links:
			l.update_save ()
		if len(self.thoughts) > 0:
			self.emit ("doc_save", self.save, self.element)
		else:
			self.emit ("doc_delete", None)

	def load_thyself (self, top_element, doc):
		for node in top_element.childNodes:
			if node.nodeName == "thought":
				self.load_thought (node)
			elif node.nodeName == "link":
				self.load_link (node)
			elif node.nodeName == "image_thought":
				self.load_image (node)
			elif node.nodeName == "drawing_thought":
				self.load_drawing (node)
			else:
				print "Warning: Unknown element type.  Ignoring: "+node.nodeName

		self.finish_loading ()

	def finish_editing (self, thought):
		do_del = thought.finish_editing ()

		if do_del:
			self.delete_thought (thought)
		else:
			thought.update_save ()
		self.update_links (thought)
		return

	def update_links (self, affected_thought):
		for l in self.links:
			if l.uses (affected_thought):
				l.update ()

	def delete_link (self, link):
		self.element.removeChild (link.element)
		link.element.unlink ()
		self.links.remove (link)

	def delete_thought (self, thought, a = None, b = None):
		self.element.removeChild (thought.element)
		thought.element.unlink ()
		self.thoughts.remove (thought)
		try:
			self.selected_thoughts.remove (thought)
			self.num_selected -= 1
		except:
			pass
		if self.current_root == thought:
			self.current_root = None
		if self.primary_thought == thought:
			self.primary_thought = None
			if self.thoughts:
				self.make_primary_root (self.thoughts[0])
		rem_links = []
		for l in self.links:
			if l.uses (thought):
				rem_links.append (l)
		for l in rem_links:
			self.delete_link (l)
		del thought

	def create_image (self, coords):
		self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.LEFT_PTR))
		try:
			mode = self.old_mode
		except:
			mode = MODE_EDITING

		self.emit ("change_mode", mode)
		# Present a dialog for the user to choose an image here
		dialog = gtk.FileChooserDialog (_("Choose image to insert"), None, gtk.FILE_CHOOSER_ACTION_OPEN, \
		(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		res = dialog.run ()
		dialog.hide ()
		if res == gtk.RESPONSE_OK:
			fname = dialog.get_filename()
			elem = self.save.createElement ("image_thought")
			extended_elem = self.save.createElement ("Extended")
			extended_element = self.save.createTextNode ("Extended")
			elem.appendChild (extended_elem)
			extended_elem.appendChild (extended_element)
			self.element.appendChild (elem)
			thought = ImageThought.ImageThought (fname, coords, self.nthoughts, elem, extended=extended_element)
			if not thought.okay:
				dialog = gtk.MessageDialog (None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
											gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
											_("Error loading file"))
				dialog.format_secondary_text (_("%s could not be read.  Please ensure its a valid image."%fname))
				dialog.run ()
				dialog.hide ()
				return
			thought.connect ("change_cursor", self.cursor_change_cb)
			self.nthoughts+=1
			if self.current_root:
				self.link_thoughts (self.current_root, thought)
			else:
				self.make_current_root (thought)

			if not self.primary_thought:
				self.make_primary_root (thought)

			self.thoughts.append (thought)
			self.invalidate ()

	def create_drawing (self, coords):
		self.window.set_cursor (gtk.gdk.Cursor (gtk.gdk.LEFT_PTR))

		elem = self.save.createElement ("drawing_thought")
		extended_elem = self.save.createElement ("Extended")
		extended_element = self.save.createTextNode ("Extended")
		elem.appendChild (extended_elem)
		extended_elem.appendChild (extended_element)
		self.element.appendChild (elem)
		thought = DrawingThought.DrawingThought (coords, self.nthoughts, elem, extended = extended_element)
		thought.connect ("change_cursor", self.cursor_change_cb)
		self.nthoughts+=1
		if self.current_root:
			self.link_thoughts (self.current_root, thought)
		else:
			self.make_current_root (thought)
		if not self.primary_thought:
			self.make_primary_root (thought)
		self.thoughts.append (thought)

	def load_image (self, node):
		elem = self.save.createElement ("image_thought")
		extended_elem = self.save.createElement ("Extended")
		extended_element = self.save.createTextNode ("Extended")
		elem.appendChild (extended_elem)
		extended_elem.appendChild (extended_element)
		thought = ImageThought.ImageThought (element = elem, load=node, extended=extended_element)
		self.element.appendChild (elem)
		thought.connect ("change_cursor", self.cursor_change_cb)
		self.thoughts.append (thought)
		if thought.identity >= self.nthoughts:
			self.nthoughts = thought.identity + 1

	def load_drawing (self, node):
		elem = self.save.createElement ("drawing_thought")
		extended_elem = self.save.createElement ("Extended")
		extended_element = self.save.createTextNode ("Extended")
		elem.appendChild (extended_elem)
		extended_elem.appendChild (extended_element)
		self.element.appendChild (elem)
		thought = DrawingThought.DrawingThought (element = elem, load=node, extended=extended_element)
		thought.connect ("change_cursor", self.cursor_change_cb)
		self.thoughts.append (thought)
		if thought.identity >= self.nthoughts:
			self.nthoughts = thought.identity + 1

	def select_thought (self, thought):
		self.emit ("change_buffer", thought.extended_buffer)
		self.selected_thoughts = [thought]
		thought.select ()
		self.num_selected = 1

	def area_close (self):
		self.save_thyself ()


	def cursor_change_cb (self, thought, cursor_type, a):
		self.window.set_cursor (gtk.gdk.Cursor (cursor_type))
		return

	def export (self, context, width, height, native):
		context.rectangle (0, 0, width, height)
		context.clip ()
		context.set_source_rgb (1.0,1.0,1.0)
		context.move_to (0,0)
		context.paint ()
		context.set_source_rgb (0.0,0.0,0.0)
		if not native:
			move_x = self.move_x
			move_y = self.move_y
		else:
			move_x = 0
			move_y = 0
		for l in self.links:
			l.export (context, move_x, move_y)
		for t in self.thoughts:
			t.export (context, move_x, move_y)

	def get_max_area (self):
		minx = 999
		maxx = -999
		miny = 999
		maxy = -999

		for t in self.thoughts:
			mx,my,mmx,mmy = t.get_max_area ()
			if mx < minx:
				minx = mx
			if my < miny:
				miny = my
			if mmx > maxx:
				maxx = mmx
			if mmy > maxy:
				maxy = mmy
		# Add a 10px border around all
		self.move_x = 10-minx
		self.move_y = 10-miny
		maxx = maxx-minx+20
		maxy = maxy-miny+20
		return (maxx,maxy)

	def get_selection_bounds (self):
		if len (self.selected_thoughts) > 0:
			return self.selected_thoughts[0].index, self.selected_thoughts[0].end_index
		else:
			return None, None

	def copy_clipboard (self, clip):
		index = self.selected_thoughts[0].index
		end = self.selected_thoughts[0].end_index

		if end > index:
			clip.set_text (self.selected_thoughts[0].text[index:end])
		else:
			clip.set_text (self.selected_thoughts[0].text[end:index])

	def cut_clipboard (self, clip):
		index = self.selected_thoughts[0].index
		end = self.selected_thoughts[0].end_index

		if end > index:
			clip.set_text (self.selected_thoughts[0].text[index:end])
		else:
			clip.set_text (self.selected_thoughts[0].text[end:index])

		# Be really cheeky here and use already existing functions -
		# Pretend a delete key event occured ;)
		self.selected_thoughts[0].handle_key (None, gtk.keysyms.Delete, 0)
		self.invalidate ()

	def paste_clipboard (self, clip):
		text = clip.wait_for_text()
		# Again, cheekily hitch onto the already existing infrastructure
		self.selected_thoughts[0].handle_key (text, None, None)
		self.invalidate ()
