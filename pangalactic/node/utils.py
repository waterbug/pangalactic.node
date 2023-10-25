# -*- coding: utf-8 -*-
"""
GUI related utility functions
"""
import os
from copy import deepcopy

from PyQt5.QtWidgets import (QApplication, QStyle, QStyleOptionViewItem,
                             QStyledItemDelegate, QTableWidgetItem)
from PyQt5.QtCore    import (Qt, QByteArray, QDataStream, QIODevice, QMimeData,
                             QSize, QVariant)
from PyQt5.QtGui     import (QAbstractTextDocumentLayout, QBrush, QColor,
                             QFont, QIcon, QPalette, QPixmap, QTextDocument)

# Louie
from louie import dispatcher

from pangalactic.core             import orb
from pangalactic.core             import state
from pangalactic.core.clone       import clone
from pangalactic.core.names       import (get_display_name, get_acu_id,
                                          get_acu_name, get_external_name,
                                          to_media_name)
from pangalactic.core.parametrics import data_elementz, parameterz
from pangalactic.core.utils.datetimes import dtstamp


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


class RqtAllocDelegate(QStyledItemDelegate):

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
            super().paint(painter, option, index)


class InfoTableItem(QTableWidgetItem):

    def __init__(self, text=None):
        if text is not None:
            super().__init__(text)
        else:
            super().__init__()
        self.isResolving = False

    def setData(self, role, value):
        super().setData(role, value)
        try:
            if self.tableWidget():
                self.tableWidget().viewport().update()
        except:
            # C++ obj got deleted
            pass


class InfoTableHeaderItem(QTableWidgetItem):

    def __init__(self, text=None):
        if text is not None:
            super().__init__(text)
        else:
            super().__init__()
        color = QColor('#ffffd1')
        self.setBackground(QBrush(color))
        font = QFont()
        fsize = font.pointSize()
        orb.log.debug(f'* header uses font size {fsize}')
        font.setWeight(QFont.Bold)
        self.setFont(font)
        self.isResolving = False


def get_all_usages(usage):
    """
    For the specified product usage, trace back to all usages that appear in
    assemblies in which it occurs as a component.

    Args:
        usage (Acu):  the specified usage
    """
    # include this usage too!
    usages = set([usage])
    for acu in usage.assembly.where_used:
        usages.add(acu)
        for usage in get_all_usages(acu):
            usages.add(usage)
    return usages

def get_all_project_usages(product):
    all_usages = set()
    projects = set()
    for acu in product.where_used:
        all_usages |= get_all_usages(acu)
    all_assemblies = set([acu.assembly for acu in all_usages])
    for a in all_assemblies:
        if a.projects_using_system:
            for psu in a.projects_using_system:
                projects.add(psu.project)
    return projects

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
    orb.log.info('* creating template from product ...')
    template = clone('Template', id=template_id, name=template_name,
                     product_type=tmpl_product_type, public=True)
    tbd = orb.get('pgefobjects:TBD')
    if product.components:
        for acu in product.components:
            pth = acu.product_type_hint or acu.component.product_type
            clone('Acu',
                  id=get_acu_id(template_id, acu.reference_designator),
                  name=get_acu_name(template_name, acu.reference_designator),
                  assembly=template, component=tbd,
                  reference_designator=acu.reference_designator,
                  product_type_hint=pth)
    # Copy any parameters or data elements the product has to the template
    parms = parameterz.get(product.oid)
    if parms:
        parameterz[template.oid] = deepcopy(parms)
    data = data_elementz.get(product.oid)
    if data:
        data_elementz[template.oid] = deepcopy(data)
    orb.log.info('  created Template instance with id "%s" ...' % (
                                                        template.id))
    return template

def create_product_from_template(template):
    """
    Create a product from the specified template.

    Args:
        template (Template):  the template to be used
    """
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
    # NOTE: get TBD product here to avoid a db commit()
    tbd = orb.get('pgefobjects:TBD')
    orb.log.info('* creating product from template ...')
    product = clone('HardwareProduct', id=product_id,
                    name=product_name, description=product_desc,
                    product_type=template.product_type, public=True)
    new_comps = 0
    if template.components:
        for acu in template.components:
            if acu.component is None:
                # if there is no component, ignore it
                continue
            elif getattr(acu.component, 'oid', '') == 'pgefobjects:TBD':
                if acu.product_type_hint:
                    # if component is TBD, use pth of acu
                    pth = acu.product_type_hint
                else:
                    # if component is TBD but no pth, ignore it
                    continue
            else:
                # if there is a real component, use its pt as the pth
                pth = acu.component.product_type
            pth_id = getattr(pth, 'id', '[unspecified product type]')
            pth_name = getattr(pth, 'name', '[unspecified product type]')
            acu_id = '-'.join([product_id, pth_id])
            acu_name = ' '.join([product_name, pth_name])
            orb.log.info(f'* creating function {acu_name} ...')
            clone('Acu', id=acu_id, name=acu_name, assembly=product,
                  component=tbd, reference_designator=acu.reference_designator,
                  product_type_hint=pth)
            new_comps += 1
    # NOTE: put product and acus all in one db commit so tree rebuild does not
    # get confused
    orb.db.commit()
    orb.log.info('  created HardwareProduct instance with id "{}" ...'.format(
                                                                   product.id))
    if new_comps:
        orb.log.info('  and {} components.'.format(new_comps))
    else:
        orb.log.info('  and no components.')
    # Copy any parameters or data elements the template has to the product
    parms = parameterz.get(template.oid)
    if parms:
        parameterz[product.oid] = deepcopy(parms)
    data = data_elementz.get(template.oid)
    if data:
        data_elementz[product.oid] = deepcopy(data)
    return product

def populate_sc_subsystems(sc):
    """
    Populate a spacecraft with a set of new black box subsystems, the use-case
    being to prepare a new spacecraft concept for collaborative development by
    a team of discipline engineers.  The presumption is that the spacecraft
    object has been instantiated from a template containing a set of empty
    subsystem "functions" (Acu instances) that specify the types of subsystems
    to be populated.

    Args:
        sc (HardwareProduct):  a product of product_type "spacecraft"
    """
    orb.log.info('* populate_sc_subsystems()')
    if sc.components:
        new_objs = []
        mod_objs = []
        NOW = dtstamp()
        local_user = orb.get(state.get('local_user_oid'))
        for acu in sc.components:
            pth = None
            if acu.component is None:
                # if there is no component, ignore it
                continue
            elif getattr(acu.component, 'oid', '') == 'pgefobjects:TBD':
                if acu.product_type_hint:
                    # if component is TBD, use pth of acu
                    pth = acu.product_type_hint
                else:
                    # if component is TBD but no pth, ignore it
                    continue
            else:
                # if there is a real component, ignore it
                continue
            if pth:
                orb.log.info(f'* creating {pth.name} ...')
                description = f'{sc.name} {pth.name}'
                p = clone('HardwareProduct', name=pth.name, product_type=pth,
                          description=description, save_hw=False)
                orb.save([p])
                acu.component = p
                # mod_datetime is critical, for acus to be updated ...
                acu.mod_datetime = NOW
                acu.modifier = local_user
                orb.save([acu])
                new_objs.append(p)
                mod_objs.append(acu)
            else:
                # if product_type_hint was not populated, ignore
                orb.log.info(f'  - "{acu.id}" had no product type hint.')
                continue
        if new_objs:
            for obj in new_objs:
                dispatcher.send('new object', obj=obj)
        if mod_objs:
            for obj in mod_objs:
                dispatcher.send('modified object', obj=obj)

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
        title += f'<font color="blue">New {cname_display}</font></h3>'
        return title
    else:
        # non-ManagedObjects don't have a significant obj.id ...
        if isinstance(obj, orb.classes['ManagedObject']):
            title += get_display_name(obj) or '[no name]'
        else:
            dname = get_display_name(obj)
            if dname == 'Unidentified':
                dname = obj.id
            title += f' <font color="purple">[{dname}]</font>'
            return title + '</h3>'
    pt = ''
    if obj.id:
        title += f' <font color="purple">[{obj.id}]</font>'
    else:
        pt = getattr(obj, 'product_type', None)
        if pt:
            obj_type_display = pt.abbreviation
        else:
            obj_type_display = cname_display
        if obj_type_display:
            title += f' <font color="purple">[{obj_type_display}]</font>'
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
    icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
    # check for a special icon for this specific object
    if getattr(obj, 'id', None):
        special_icon_path = os.path.join(icon_dir, obj.id + state['icon_type'])
        if os.path.exists(special_icon_path):
            return special_icon_path
    if isinstance(obj, orb.classes['PortType']):
        # special icons for PortTypes
        prefix = 'PortType_' + obj.id
        icon_path = os.path.join(icon_dir, prefix + state['icon_type'])
        if os.path.exists(icon_path):
            return icon_path
    if isinstance(obj, orb.classes['PortTemplate']):
        # special icons for PortTemplates
        prefix = 'PortTemplate_' + obj.type_of_port.id
        icon_path = os.path.join(icon_dir, prefix + state['icon_type'])
        if os.path.exists(icon_path):
            return icon_path
    # ManagedObject has the "public" attribute, but Product is the only class
    # that actually applies it ...
    if (isinstance(obj, orb.classes['Product'])
        and not isinstance(obj, orb.classes['Template'])):
        if obj.public:
            if obj.components:
                # white box
                if obj.frozen:
                    return os.path.join(icon_dir,
                        'frz_wbox' + state['icon_type'])
                else:
                    return os.path.join(icon_dir, 'box' + state['icon_type'])
            else:
                # black box
                if obj.frozen:
                    return os.path.join(icon_dir,
                        'frz_bbox' + state['icon_type'])
                else:
                    return os.path.join(icon_dir,
                        'black_box' + state['icon_type'])
        else:
            # if obj is not public, use the 'cloakable' icon
            if obj.components:
                if obj.frozen:
                    return os.path.join(icon_dir,
                        'frz_wbox_cloakable' + state['icon_type'])
                else:
                    return os.path.join(icon_dir,
                        'cloakable' + state['icon_type'])
            else:
                if obj.frozen:
                    return os.path.join(icon_dir,
                        'frz_bbox_cloakable' + state['icon_type'])
                else:
                    return os.path.join(icon_dir,
                        'black_cloakable' + state['icon_type'])
    cname = obj.__class__.__name__
    if ((cname == 'Person') and
        obj.id in (state.get('active_users') or [])):
        return os.path.join(icon_dir, 'green_box' + state['icon_type'])
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
        icon_path = get_icon_path(obj)
        if not os.path.exists(icon_path):
            # if no generated icon is found, fall back to default icons
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            if obj.__class__.__name__ == 'Project':
                icon_path = os.path.join(icon_dir,
                                         'favicon' + state['icon_type'])
            else:
                icon_path = os.path.join(
                                icon_dir, 'box' + state['icon_type'])
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
    if obj:
        data = QByteArray()
        stream = QDataStream(data, QIODevice.WriteOnly)
        mime_data = QMimeData()
        if isinstance(obj, str):
            # if obj is a string, it's just a parameter id
            stream << QByteArray(obj.encode('utf-8'))
            mime_data.setData('application/x-pgef-parameter-id', data)
        else:
            obj_oid = QByteArray(obj.oid.encode('utf-8'))
            obj_id = QByteArray(obj.id.encode('utf-8'))
            name = obj.name or '[no name]'
            obj_name = QByteArray(name.encode('utf-8'))
            cname = obj.__class__.__name__.encode('utf-8')
            ba_cname = QByteArray(cname)
            stream << icon << obj_oid << obj_id << obj_name << ba_cname
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
        data (str):  parameter id (for 'application/x-pgef-parameter-id')
        - or (for anything else) -
        data (tuple):  icon, oid, id, name, class name
    """
    if media_type == 'application/x-pgef-parameter-id':
        data = event.mimeData().data(media_type)
        stream = QDataStream(data, QIODevice.ReadOnly)
        pid_ba = QByteArray()
        stream >> pid_ba
        pid = bytes(pid_ba).decode('utf-8')
        return pid
    else:
        data = event.mimeData().data(media_type)
        stream = QDataStream(data, QIODevice.ReadOnly)
        icon = QIcon()
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

