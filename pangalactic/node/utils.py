# -*- coding: utf-8 -*-
"""
GUI related utility functions
"""
from __future__ import division
from builtins import bytes
from future import standard_library
standard_library.install_aliases()
from builtins import range
import os, sys
from copy import deepcopy
from uuid import uuid4

from PyQt5.QtWidgets import (QApplication, QStyle, QStyleOptionViewItem,
                             QStyledItemDelegate)
from PyQt5.QtCore    import (Qt, QByteArray, QDataStream, QIODevice, QMimeData,
                             QSize, QVariant)
from PyQt5.QtGui     import (QAbstractTextDocumentLayout, QIcon, QPalette,
                             QPixmap, QTextDocument)

# SqlAlchemy
from sqlalchemy import ForeignKey

from pangalactic.core             import state
from pangalactic.core.utils.meta  import (display_name, get_acu_id,
                                          get_acu_name, get_external_name,
                                          to_media_name)
from pangalactic.core.parametrics import (add_default_parameters, parameterz,
                                          refresh_componentz)
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp


def clone(what, include_ports=True, include_components=True,
          generate_id=False, **kw):
    """
    Create a new object either (1) from keywords or (2) by copying an
    existing object.  NOTE:  clone() does not save/commit the object, so
    orb.save() or orb.db.commit() must be called after cloning.

    (1) If `what` is a string, create a new instance of the schema with
    that name, and assign it the values in the `kw` dict.  If the named
    class is a subtype of 'Product', the new instance will be a
    "working version" and will receive a version and version_sequence only
    when frozen.

    (2) If `what` is an instance of a subtype of `Identifiable`, create a
    clone of that instance.  If it is a subtype of 'Product', it will be
    checked for 'version' -- if not None, it is versioned.

    Any keyword arguments supplied will be used as attributes if they are
    in the schema (overriding those of the provided object in case 2).
    If a oid is not provided, a new oid guaranteed to be unique will be
    auto-generated.  If not specified, the following attributes will also
    be auto-generated:

        creator and modifier = local_user
        owner = current project or PGANA
        [create|mod]_datetime = current datetime

    Default values are used where appropriate.

    Args:
        what (str or Identifiable): schema name or object to be cloned

    Keyword Args:
        include_ports (bool): if an object with ports is being cloned, give the
            clone the same ports
        include_components (bool): if an object with components is being
            cloned, give the clone the same components
        generate_id (bool): if True, an opaque id will be auto-generated
        kw (dict):  attributes for the clone
    """
    orb.log.info('* clone({})'.format(what))
    new = False
    recompute_needed = False
    if what in orb.classes:
        # 'what' is a class name -- create a new instance from scratch
        # TODO:  validation: every new object *must* have 'id' value
        # TODO:  validation: a ParameterDefinition must have an 'id' value
        # that is unique among ParameterDefinitions
        # NOTE: possible future enhancement: parameter namespaces
        new = True
        cname = what
        schema = orb.schemas[cname]
        fields = schema['fields']
        cls = orb.classes[cname]
        newkw = dict([(a, kw[a]) for a in kw if a in fields])
    else:
        # 'what' is a domain object -- clone it to create a new instance
        # TODO: URGENT!!  add logic above to object clones
        # TODO: URGENT!!  exception handling in case what is not a domain obj
        obj = what
        cname = obj.__class__.__name__
        schema = orb.schemas[cname]
        fields = schema['fields']
        non_fk_fields = {a : fields[a] for a in fields
                         if fields[a]['field_type'] is not ForeignKey}
        cls = obj.__class__
        newkw = {}
        # populate all fields passed in kw args and all non-fk fields from obj
        # -- fk fields will be handled in special cases ...
        for a in fields:
            if a in kw:
                newkw[a] = kw[a]
            elif a in non_fk_fields:
                newkw[a] = getattr(obj, a)
        newkw['oid'] = str(uuid4())
    # generate a unique oid if one is not provided
    if not newkw.get('oid'):
        newkw['oid'] = str(uuid4())
    orb.new_oids.append(newkw['oid'])
    if generate_id and not newkw.get('id'):
        # this is only needed for objects whose 'id' does not need to be
        # significant and/or human-intelligible, but should still exist
        newkw['id'] = '_'.join([cname, newkw['oid']])
    orb.log.info('  new %s oid: %s)' % (cname, newkw['oid']))
    NOW = dtstamp()
    newkw.update(dict([(dts, NOW) for dts in ['create_datetime',
                                              'mod_datetime']]))
    local_user = orb.get(state.get('local_user_oid'))
    if local_user:
        if 'creator' in fields:
            newkw['creator'] = local_user
        if 'modifier' in fields:
            newkw['modifier'] = local_user
    if not new and orb.is_versioned(obj):
        # TODO:  add interface functions for "clone to create new version"
        # current clone "copies" (i.e. creates a new object, not a version)
        newkw['version_sequence'] = 0
        newkw['version'] = None
        newkw['frozen'] = False
        newkw['iteration'] = 0
    if issubclass(orb.classes[cname], orb.classes['ManagedObject']):
        owner = orb.get(state.get('project'))  # None if not set
        newkw['owner'] = owner
    new_obj = cls(**newkw)
    orb.db.add(new_obj)
    if not new and parameterz.get(getattr(obj, 'oid', None)):
        # When cloning an existing object that has parameters, copy its
        # parameters to the clone
        new_parameters = deepcopy(parameterz[obj.oid])
        parameterz[newkw['oid']] = new_parameters
        recompute_needed = True
    # operations specific to Products ...
    if isinstance(new_obj, orb.classes['Product']):
        recompute_needed = True
        if new:
            # NOTE:  this will add both class-specific and ProductType-specific
            # default parameters, as well as any custom parameters specified in
            # "config" and "prefs" for HardwareProduct instances ...
            add_default_parameters(orb, new_obj)
        else:
            # the clone gets the product_type of the original object
            new_obj.product_type = obj.product_type
            new_obj.derived_from = obj
            # if we are including ports, add them ...
            if include_ports and getattr(obj, 'ports', None):
                for port in obj.ports:
                    clone('Port', id=port.id, name=port.name,
                          type_of_port=port.type_of_port, of_product=new_obj,
                          creator=new_obj.creator, modifier=new_obj.creator,
                          create_datetime=NOW, mod_datetime=NOW)
            # if we are including components, add them ...
            if include_components and getattr(obj, 'components', None):
                for acu in obj.components:
                    ref_des = orb.get_next_ref_des(new_obj, acu.component)
                    clone('Acu', 
                          id=get_acu_id(new_obj.id, ref_des),
                          name=get_acu_name(new_obj.name, ref_des),
                          assembly=new_obj, component=acu.component,
                          product_type_hint=acu.component.product_type,
                          reference_designator=ref_des,
                          creator=new_obj.creator, modifier=new_obj.creator,
                          create_datetime=NOW, mod_datetime=NOW)
                refresh_componentz(orb, new_obj)
    if recompute_needed:
        orb.recompute_parmz()
    return new_obj

def create_template_from_product(product):
    """
    Create a template from the specified product.

    Args:
        product (Product):  the product to be used
    """
    # cname = product.__class__.__name__
    if not isinstance(product, orb.classes['Product']):
        # FIXME: need to raise an error here and display a warning to the
        # user
        return
    project_oid = state.get('project')
    project_id = getattr(orb.get(project_oid), 'id', '')
    tmpl_product_type = product.product_type
    pt_id = getattr(tmpl_product_type, 'id', 'Generic')
    pt_name = getattr(tmpl_product_type, 'name', 'Generic')
    if project_id:
        template_id = '_'.join([project_id, pt_id.lower(), 'template'])
        template_name = ' '.join([project_id, pt_name, 'Template'])
    else:
        template_id = '_'.join([pt_id.lower(), 'template'])
        template_name = ' '.join([pt_name, 'Template'])
    orb.log.info('* create_template_from_product')
    template = clone('Template', id=template_id, name=template_name,
                     product_type=tmpl_product_type, public=True)
    tbd = orb.get('pgefobjects:TBD')
    if product.components:
        for acu in product.components:
            pth = acu.product_type_hint or acu.component.product_type
            clone('Acu', id=acu.id, name=acu.name,
                  assembly=template, component=tbd,
                  reference_designator=acu.reference_designator,
                  product_type_hint=pth)
    # TODO:  assign parameters to template ...
    parms = parameterz.get(product.oid)
    if parms:
        parameterz[template.oid] = deepcopy(parms)
    orb.log.info('  created Template instance with id "%s" ...' % (
                                                        template.id))
    return template

def create_product_from_template(template):
    """
    Create a product from the specified template.

    Args:
        template (Template):  the template to be used
    """
    # TODO:  this needs to use the New Product Wizard ...
    #        [1] 'id' needs to be unique
    if not isinstance(template, orb.classes['Template']):
        # FIXME: need to raise an error here and display a warning to the
        # user
        return
    project_oid = state.get('project')
    if project_oid:
        project_id = getattr(orb.get(project_oid), 'id')
    else:
        project_id = 'X'
    pt_id = getattr(template.product_type, 'id', 'product')
    pt_name = getattr(template.product_type, 'name', 'Product')
    product_id = '-'.join([project_id, pt_id])
    product_name = ' '.join([project_id, pt_name])
    product_desc = ' '.join([project_id, pt_name])
    orb.log.info('* create_product_from_template')
    product = clone('HardwareProduct', id=product_id,
                    name=product_name, description=product_desc,
                    product_type=template.product_type,
                    public=True)
    tbd = orb.get('pgefobjects:TBD')
    if template.components:
        for acu in template.components:
            pth = acu.product_type_hint or acu.component.product_type
            pth_id = getattr(pth, 'id', '[unspecified product type]')
            pth_name = getattr(pth, 'name', '[unspecified product type]')
            acu_id = '-'.join([product_id, pth_id])
            acu_name = ' '.join([product_name, pth_name])
            clone('Acu', id=acu_id, name=acu_name, assembly=product,
                  component=tbd, reference_designator=acu.reference_designator,
                  product_type_hint=pth)
    orb.log.info('  created HardwareProduct instance with id "%s" ...' % (
                                                               product.id))
    return product

def get_object_title(obj, new=False):
    """
    Generate a rich text title for a widget based on object metadata.

    Args:
        obj (a PGEF object):  object whose title is to be gotten
        new (bool):  flag indicating whether the object is newly created (i.e.,
            not yet named)
    """
    if not obj:
        return ''
    cname = obj.__class__.__name__
    title = '<h3>'
    cname_display = get_external_name(cname)
    if new:
        title += '<font color="blue">New {}</font>'.format(cname_display)
    else:
        title += display_name(obj) or '[no name]'
    pt = ''
    if hasattr(obj, 'product_type'):
        pt = getattr(obj.product_type, 'name', cname_display)
    if pt:
        title += ' <font color="purple">[{}]</font>'.format(pt)
    return title + '</h3>'

def get_icon_path(obj):
    """
    Get the path to the image file for an object's icon (which may or may
    not exist).

    Args:
        obj (object):  the object

    Returns:
        path (str):  path for an icon image file.
    """
    # first, check whether object is cloaked
    icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
    if hasattr(obj, 'public') and not obj.public:
        # if obj is not public, use the 'cloakedable' icon
        return os.path.join(icon_dir, 'cloakable' + state['icon_type'])
    # check for a special icon for this specific object
    if getattr(obj, 'id', None):
        special_icon_path = os.path.join(icon_dir, obj.id + state['icon_type'])
        if os.path.exists(special_icon_path):
            return special_icon_path
    cname = obj.__class__.__name__
    # check for a special icon for this class
    class_icon_path = os.path.join(icon_dir, cname + state['icon_type'])
    if os.path.exists(class_icon_path):
        return class_icon_path
    # check for a special icon in the icon vault (runtime-generated icons)
    icon_vault_path = os.path.join(orb.icon_vault, cname)
    if not os.path.exists(icon_vault_path):
        os.makedirs(icon_vault_path)
    if getattr(obj, 'id', None):
        return os.path.join(icon_vault_path, obj.id+state['icon_type'])
    return ''

def get_pixmap(obj):
    """
    Get the icon pixmap for a PGEF object, returning a default pixmap ("box")
    if none is found.

    Args:
        obj (a PGEF object):  object whose icon is to be gotten
    """
    if obj:
        # if no generated icon is found, fall back to default icons
        icon_path = get_icon_path(obj)
        if not os.path.exists(icon_path):
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            if obj.__class__.__name__ == 'Project':
                icon_path = os.path.join(icon_dir,
                                         'favicon' + state['icon_type'])
            else:
                icon_path = os.path.join(icon_dir, 'box' + state['icon_type'])
        return QPixmap(icon_path)
    else:
        return QVariant()

def create_mime_data(obj, icon):
    """
    Create a QMimeData instance to represent the content of an object whose
    class and schema are known to the orb.  Used for drag and drop functions.

    Args:
        obj (Identifiable):  the object (CAUTION: obj *must* be a instance of
            Identifiable or one of its subclasses -- this check must be done
            before calling create_mime_data)
        icon (QIcon):  icon associated with the object

    Returns:
        data (QMimeData):  contents are:  icon, oid, id, name, class name
    """
    # TODO:  provide a default icon in case icon is empty
    if sys.version_info < (3, 0):
        # python 2 version
        if obj:
            data = QByteArray()
            stream = QDataStream(data, QIODevice.WriteOnly)
            obj_oid = QByteArray(str(obj.oid))
            obj_id = QByteArray(str(obj.id))
            name = obj.name or u'[no name]'
            obj_name = QByteArray(name.encode('utf-8'))
            cname = obj.__class__.__name__
            # for Product and its subtypes, 
            ba_cname = QByteArray(cname)
            stream << icon << obj_oid << obj_id << obj_name << ba_cname
            mime_data = QMimeData()
            mime_data.setData(to_media_name(obj.__class__.__name__), data)
            return mime_data
        else:
            # if no obj, return an empty QMimeData object
            return QMimeData()
    else:
        # python 3 version
        if obj:
            data = QByteArray()
            stream = QDataStream(data, QIODevice.WriteOnly)
            obj_oid = QByteArray(obj.oid.encode('utf-8'))
            obj_id = QByteArray(obj.id.encode('utf-8'))
            name = obj.name or u'[no name]'
            obj_name = QByteArray(name.encode('utf-8'))
            cname = obj.__class__.__name__.encode('utf-8')
            # for Product and its subtypes, 
            ba_cname = QByteArray(cname)
            stream << icon << obj_oid << obj_id << obj_name << ba_cname
            mime_data = QMimeData()
            mime_data.setData(to_media_name(obj.__class__.__name__), data)
            return mime_data
        return QMimeData()


def extract_mime_data(event, media_type):
    """
    Extract contents of a drop event's mime data.

    Args
        event (QDropEvent):  the drop event
        media_type (str):  the expected media_type

    Returns:
        data (tuple):  icon, oid, id, name, class name
    """
    data = event.mimeData().data(media_type)
    stream = QDataStream(data, QIODevice.ReadOnly)
    icon = QIcon()
    if sys.version_info < (3, 0):
        # python 2 version
        obj_oid = QByteArray()
        obj_id = QByteArray()
        obj_name = QByteArray()
        obj_cname = QByteArray()
        stream >> icon >> obj_oid >> obj_id >> obj_name >> obj_cname
        name = str(obj_name).decode('utf-8')
        return icon, str(obj_oid), str(obj_id), name, str(obj_cname)
    else:
        # python 3 version
        oid_ba = QByteArray()
        id_ba = QByteArray()
        name_ba = QByteArray()
        cname_ba = QByteArray()
        stream >> icon >> oid_ba >> id_ba >> name_ba >> cname_ba
        obj_oid = bytes(oid_ba).decode('utf-8')
        obj_id = bytes(id_ba).decode('utf-8')
        obj_name = bytes(name_ba).decode('utf-8')
        obj_cname = bytes(cname_ba).decode('utf-8')
        return icon, obj_oid, obj_id, obj_name, obj_cname


def extract_mime_content(data, media_type):
    """
    Extract content from mime data.

    Args
        data (QMimeData):  the QMimeData object
        media_type (str):  the expected media_type

    Returns:
        stuff (tuple):  icon, oid, id, name, class name
    """
    content = data.data(media_type)
    stream = QDataStream(content, QIODevice.ReadOnly)
    icon = QIcon()
    if sys.version_info < (3, 0):
        # python 2 version
        obj_oid = QByteArray()
        obj_id = QByteArray()
        obj_name = QByteArray()
        obj_cname = QByteArray()
        stream >> icon >> obj_oid >> obj_id >> obj_name >> obj_cname
        name = str(obj_name).decode('utf-8')
        return icon, str(obj_oid), str(obj_id), name, str(obj_cname)
    else:
        # python 3 version
        oid_ba = QByteArray()
        id_ba = QByteArray()
        name_ba = QByteArray()
        cname_ba = QByteArray()
        stream >> icon >> oid_ba >> id_ba >> name_ba >> cname_ba
        obj_oid = bytes(oid_ba).decode('utf-8')
        obj_id = bytes(id_ba).decode('utf-8')
        obj_name = bytes(name_ba).decode('utf-8')
        obj_cname = bytes(cname_ba).decode('utf-8')
        return icon, obj_oid, obj_id, obj_name, obj_cname


def white_to_transparent(img):
    """
    Convert white bg pixels to transparent.
    """
    img = img.convert("RGBA")
    pixdata = img.load()
    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if pixdata[x, y] == (255, 255, 255, 255):
                pixdata[x, y] = (255, 255, 255, 0)
    return img


def make_parm_html(parm_id):
    parts = parm_id.split('_')
    if len(parts) > 1:
        return '{}<sub>{}</sub>'.format(parts[0], parts[1])
    else:
        return parm_id


class HTMLDelegate(QStyledItemDelegate):

    def paint(self, painter, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options,index)
        if options.widget is None:
            style = QApplication.style()
        else:
            style = options.widget.style()
        doc = QTextDocument()
        doc.setHtml(options.text)
        options.text = ""
        style.drawControl(QStyle.CE_ItemViewItem, options, painter)

        ctx = QAbstractTextDocumentLayout.PaintContext()
        # Highlighting text if item is selected
        # if (option.state & QStyle::State_Selected)
            # ctx.palette.setColor(QPalette::Text,
            # option.palette.color(QPalette::Active,
            # QPalette::HighlightedText));
        textRect = style.subElementRect(QStyle.SE_ItemViewItemText, options)
        painter.save()
        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options,index)
        doc = QTextDocument()
        doc.setHtml(options.text)
        doc.setTextWidth(options.rect.width())
        return QSize(doc.idealWidth(), doc.size().height())


class ReqAllocDelegate(QStyledItemDelegate):

    # def __init__(self, parent=None):
        # super(ReqAllocDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            option.backgroundBrush = index.data(Qt.BackgroundRole)
            option.palette.setBrush(QPalette.Highlight, option.backgroundBrush)
            painter.fillRect(option.rect, option.palette.highlight())
            # draw icon
            icon_rect = option.rect
            icon_rect.setLeft(icon_rect.left()+3)
            option.widget.style().drawItemPixmap(painter, icon_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                index.data(Qt.DecorationRole))
            # draw text
            text_rect = option.rect
            text_rect.setLeft(text_rect.left()+22)
            option.widget.style().drawItemText(painter, text_rect,
                                               Qt.AlignLeft | Qt.AlignVCenter,
                                               option.palette, True,
                                               index.data(Qt.DisplayRole))
            # QStyledItemDelegate.paint(self, painter, option, index)
        else:
            super(ReqAllocDelegate, self).paint(painter, option, index)

