# -*- coding: utf-8 -*-
"""
GUI related utility functions
"""
import os
from copy import deepcopy
from uuid import uuid4

from PyQt5.QtWidgets import (QApplication, QStyle, QStyleOptionViewItem,
                             QStyledItemDelegate)
from PyQt5.QtCore    import (Qt, QByteArray, QDataStream, QIODevice, QMimeData,
                             QSize, QVariant)
from PyQt5.QtGui     import (QAbstractTextDocumentLayout, QIcon, QPalette,
                             QPixmap, QTextDocument)

# Louie
from louie import dispatcher

# SqlAlchemy
from sqlalchemy import ForeignKey

from pangalactic.core             import state
from pangalactic.core.names       import (get_display_name, get_acu_id,
                                          get_acu_name, get_external_name,
                                          get_next_port_seq, get_next_ref_des,
                                          get_port_abbr, get_port_id,
                                          get_port_name, to_media_name)
from pangalactic.core.parametrics import (add_default_data_elements,
                                          add_default_parameters,
                                          data_elementz, get_pval,
                                          parameterz, set_pval,
                                          refresh_componentz)
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp


def clone(what, include_ports=True, include_components=True,
          include_specified_components=None, generate_id=False,
          flatten=False, **kw):
    """
    Create a new object either (1) from a class using keywords or (2) by
    copying an existing object.  NOTE:  clone() does not save/commit the
    object, so orb.save() or orb.db.commit() must be called after cloning.

    (1) If `what` is a string, create a new instance of the class with
    that name, and assign it the values in the `kw` dict.  If the named
    class is a subtype of 'Product', the new instance will be a
    "working version" and will receive a version and version_sequence only
    when frozen.

    (2) If `what` is an instance of a subtype of `Identifiable`, create a
    clone of that instance.  If it is a subtype of 'Product', it will be
    checked for 'version' -- if not None, it is versioned.

    Any keyword arguments supplied will be used as attributes if they are
    in the schema (overriding those of the provided object in case 2).  If a
    oid is not provided, a new oid guaranteed to be unique will be generated.
    If not specified, the following attributes will also be generated:

        creator and modifier = local_user
        owner = current project or PGANA
        [create|mod]_datetime = current datetime

    Default values are used where appropriate.

    Args:
        what (str or Identifiable): class name or object to be cloned

    Keyword Args:
        include_ports (bool): if an object with ports is being cloned, give the
            clone the same ports
        include_components (bool): if the object being cloned has components,
            create new Acus for the clone to have all the same components
        include_specified_components (list of Acu instances or None): create
            new Acus for the clone to have ONLY the specified components (NOTE
            THAT include_specified_components OVERRIDES include_components)
        generate_id (bool): if True, an id will be auto-generated -- always
            True if obj is a subclass of Product
        flatten (bool):  for a black box clone (no components), populate the
            Mass, Power, and Data Rate parameters with the corresponding 'CBE'
            parameter values from the original object
        kw (dict):  attributes for the clone
    """
    orb.log.info('* clone({})'.format(what))
    from_object = True
    recompute_needed = False
    if what in orb.classes:
        # 'what' is a class name -- create a new instance from scratch
        # TODO:  validation: every new object *must* have 'id' value, which
        # *should* be unique (at least within its Class of objects)
        from_object = False
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
            # exclude "derived_from"
            if a in kw and a != 'derived_from':
                newkw[a] = kw[a]
            elif a in non_fk_fields:
                newkw[a] = getattr(obj, a)
        # new generated oid
        newkw['oid'] = str(uuid4())
        # standard attributes of any Identifiable ...
        newkw['name'] = 'clone of ' + (obj.name or 'anonymous')
        newkw['abbreviation'] = 'cloned-' + (obj.abbreviation or 'obj')
        newkw['description'] = 'cloned description: ' + (obj.description
                                                         or '[empty]')
        clone_comment = 'cloned from ' + obj.id
        if obj.comment:
            new_comment = '\n'.join([clone_comment, '[original comment was:',
                                     obj.comment + ']'])
        else:
            new_comment = clone_comment
        newkw['comment'] = new_comment
    # generate a unique oid if one is not provided
    if not newkw.get('oid'):
        newkw['oid'] = str(uuid4())
    orb.new_oids.append(newkw['oid'])
    if ((generate_id and not issubclass(cls, orb.classes['Product']))
        and not newkw.get('id')):
        orb.log.info('  generating arbitrary id ...')
        # this is only needed for objects for which an 'id' is required
        # but does not need to be significant and/or human-intelligible
        # (ids for subclasses of 'Product' will be autogenerated below ...)
        newkw['id'] = '-'.join([cname, newkw['oid'][:5]])
        orb.log.info('  id: "{}"'.format(newkw['id']))
    orb.log.info('  new %s oid: %s)' % (cname, newkw['oid']))
    NOW = dtstamp()
    newkw.update(dict([(dts, NOW) for dts in ['create_datetime',
                                              'mod_datetime']]))
    local_user = orb.get(state.get('local_user_oid'))
    if issubclass(cls, orb.classes['Modelable']) and local_user:
        if 'creator' in fields:
            newkw['creator'] = local_user
        if 'modifier' in fields:
            newkw['modifier'] = local_user
    if from_object and issubclass(cls, orb.classes['Product']):
        # TODO:  add interface functions for "clone to create new version"
        # current clone "copies" (i.e. creates a new object, not a version)
        ver_seq = kw.get('version_sequence')
        if isinstance(ver_seq, int):
            # if an integer version_sequence is specified, use it (this will be
            # the case if clone() is being used to create a new version)
            newkw['version_sequence'] = ver_seq
        else:
            # otherwise, assume this is a distinct object, not a new version of
            # the cloned object, and set to 0
            newkw['version_sequence'] = 0
        newkw['version'] = None
        newkw['frozen'] = False
        newkw['iteration'] = 0
        if isinstance(obj, orb.classes['HardwareProduct']):
            # the clone gets the product_type of the original object
            newkw['product_type'] = obj.product_type
    if issubclass(orb.classes[cname], orb.classes['ManagedObject']):
        owner = orb.get(state.get('project'))  # None if not set
        if owner:
            newkw['owner'] = owner
        else:
            # use PGANA
            pgana = orb.get('pgefobjects:PGANA')
            newkw['owner'] = pgana
    new_obj = cls(**newkw)
    orb.db.add(new_obj)
    # When cloning an existing object that has parameters or data elements,
    # copy them to the clone
    if from_object:
        if parameterz.get(getattr(obj, 'oid', None)):
            new_parameters = deepcopy(parameterz[obj.oid])
            parameterz[newkw['oid']] = new_parameters
            recompute_needed = True
        if from_object and data_elementz.get(getattr(obj, 'oid', None)):
            new_data = deepcopy(data_elementz[obj.oid])
            data_elementz[newkw['oid']] = new_data
    else:   # NOT from_object -- new_obj is a brand-new object
        # NOTE:  this will add both class-specific and (for HardwareProducts)
        # ProductType-specific default parameters, as well as any custom
        # parameters specified in "config" and "prefs" for HardwareProduct
        # instances ...
        add_default_data_elements(new_obj)
        add_default_parameters(new_obj)
    # operations specific to HardwareProducts ...
    if isinstance(new_obj, orb.classes['HardwareProduct']):
        new_ports = []
        new_acus = []
        recompute_needed = True
        if from_object:
            # DO NOT use "derived_from"!  It creates an FK relationship that
            # prohibits the original object from being deleted -- the
            # "derived_from" attribute is deprecated and will be removed at
            # some point.
            # new_obj.derived_from = obj
            # if we are including ports, add them ...
            if include_ports and getattr(obj, 'ports', None):
                Port = orb.classes['Port']
                for port in obj.ports:
                    seq = get_next_port_seq(new_obj, port.type_of_port)
                    port_oid = str(uuid4())
                    port_id = get_port_id(port.of_product.id,
                                          port.type_of_port.id,
                                          seq)
                    port_name = get_port_name(port.of_product.name,
                                              port.type_of_port.name, seq)
                    port_abbr = get_port_abbr(port.type_of_port.abbreviation,
                                              seq)
                    p = Port(oid=port_oid, id=port_id, name=port_name,
                             abbreviation=port_abbr,
                             type_of_port=port.type_of_port,
                             of_product=new_obj, creator=new_obj.creator,
                             modifier=new_obj.creator, create_datetime=NOW,
                             mod_datetime=NOW)
                    new_ports.append(p)
                    orb.db.add(p)
            # if we are including components, add them ...
            # NOTE:  "include_specified_components" overrides
            # "include_components" -- if components are specified, ONLY those
            # components will be included
            if (include_specified_components and
                isinstance(include_specified_components, list)):
                orb.log.debug('  - include_specified_components ...')
                Acu = orb.classes['Acu']
                for acu in include_specified_components:
                    if not isinstance(acu, orb.classes['Acu']):
                        orb.log.debug(f'    non-Acu skipped: {acu.id}')
                        continue
                    acu_oid = str(uuid4())
                    ref_des = get_next_ref_des(new_obj, acu.component)
                    acu = Acu(oid=acu_oid,
                              id=get_acu_id(new_obj.id, ref_des),
                              name=get_acu_name(new_obj.name, ref_des),
                              assembly=new_obj, component=acu.component,
                              product_type_hint=acu.product_type_hint,
                              reference_designator=ref_des,
                              creator=new_obj.creator,
                              modifier=new_obj.creator, create_datetime=NOW,
                              mod_datetime=NOW)
                    new_acus.append(acu)
                    orb.db.add(acu)
                refresh_componentz(new_obj)
            elif include_components and getattr(obj, 'components', None):
                Acu = orb.classes['Acu']
                for acu in obj.components:
                    acu_oid = str(uuid4())
                    ref_des = get_next_ref_des(new_obj, acu.component)
                    acu = Acu(oid=acu_oid,
                              id=get_acu_id(new_obj.id, ref_des),
                              name=get_acu_name(new_obj.name, ref_des),
                              assembly=new_obj, component=acu.component,
                              product_type_hint=acu.product_type_hint,
                              reference_designator=ref_des,
                              creator=new_obj.creator,
                              modifier=new_obj.creator, create_datetime=NOW,
                              mod_datetime=NOW)
                    new_acus.append(acu)
                    orb.db.add(acu)
                refresh_componentz(new_obj)
            elif (not include_components and not include_specified_components
                  and flatten):
                # black box clone with m, P, R_D assigned the CBE values from
                # the original object
                for pid in ['m', 'P', 'R_D']:
                    pid_cbe = pid + '[CBE]'
                    cbe_val = get_pval(obj.oid, pid_cbe)
                    set_pval(new_obj.oid, pid, cbe_val)
        # the 'id' must be generated *after* the product_type is assigned
        new_obj.id = orb.gen_product_id(new_obj)
        new_objs = []
        new_objs += new_ports
        new_objs += new_acus
        dispatcher.send(signal='new hardware clone', product=new_obj,
                        objs=new_objs)
    if recompute_needed:
        orb.recompute_parmz()
    return new_obj

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


def make_parm_html(parm_id):
    if not isinstance(parm_id, str):
        return '<b>oops</b>'
    if '[' in parm_id:
        base, tail = parm_id.split('[')
        ctxt = '[' + tail
    else:
        base = parm_id
        ctxt = ''
    parts = base.split('_')
    if len(parts) > 1:
        return '<b>{}<sub>{}</sub>{}</b>'.format(parts[0], parts[1], ctxt)
    else:
        return '<b>{}{}</b>'.format(base, ctxt)


def make_de_html(deid):
    if not isinstance(deid, str):
        return '<b>oops</b>'
    parts = deid.split('_')
    name_parts = [p.capitalize() for p in parts]
    if len(parts) > 1:
        return '<b>' + ' '.join(name_parts) + '</b>'
    elif deid == 'TRL':
        # yes, ugly :(
        return '<b>TRL</b>'
    else:
        return f'<b>{deid.capitalize()}</b>'


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

