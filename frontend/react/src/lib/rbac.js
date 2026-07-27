export const ROLE_ADMIN = "admin";
export const ROLE_MANAGER = "manager";
export const ROLE_PRINCIPAL = "principal";
export const ROLE_DIRECTOR = "director";
export const ROLE_CLASS_TEACHER = "class_teacher";

export const CAPABILITY_OVERVIEW_VIEW = "overview:view";
export const CAPABILITY_ATTENDANCE_VIEW = "attendance:view";
export const CAPABILITY_ATTENDANCE_MANAGE = "attendance:manage";
export const CAPABILITY_ATTENDANCE_EXPORT = "attendance:export";
export const CAPABILITY_PEOPLE_VIEW = "people:view";
export const CAPABILITY_PEOPLE_MANAGE = "people:manage";
export const CAPABILITY_CAMERAS_VIEW = "cameras:view";
export const CAPABILITY_CAMERAS_MANAGE = "cameras:manage";
export const CAPABILITY_RECOGNITION_VIEW = "recognition:view";
export const CAPABILITY_RECOGNITION_MANAGE = "recognition:manage";
export const CAPABILITY_ACTIVITIES_VIEW = "activities:view";
export const CAPABILITY_EMOTIONS_VIEW = "emotions:view";
export const CAPABILITY_ANALYTICS_VIEW = "analytics:view";
export const CAPABILITY_SYSTEM_ADMIN = "system:admin";

export function getRoleLabel(role) {
  if (role === ROLE_ADMIN) {
    return "Administrator";
  }
  if (role === ROLE_MANAGER) {
    return "Manager";
  }
  if (role === ROLE_PRINCIPAL) {
    return "Principal";
  }
  if (role === ROLE_DIRECTOR) {
    return "Director";
  }
  if (role === ROLE_CLASS_TEACHER) {
    return "Class Teacher";
  }
  return "Workspace User";
}

export function hasCapability(user, capability) {
  return Boolean(user?.capabilities?.includes(capability));
}

export function canManagePeople(user) {
  return hasCapability(user, CAPABILITY_PEOPLE_MANAGE);
}

export function canManageCameras(user) {
  return hasCapability(user, CAPABILITY_CAMERAS_MANAGE);
}
