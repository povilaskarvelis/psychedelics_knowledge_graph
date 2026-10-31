import {useFrame, useThree} from '@react-three/fiber';
import * as THREE from 'three';

// Deterministic camera: pose = {pos:[x,y,z], look:[x,y,z], fov, roll}
export const applyPose = (cam, pose) => {
  cam.position.set(...pose.pos);
  cam.up.set(Math.sin(pose.roll || 0), Math.cos(pose.roll || 0), 0);
  cam.lookAt(...pose.look);
  if (pose.fov && cam.fov !== pose.fov) { cam.fov = pose.fov; }
  cam.near = pose.near ?? 0.05;
  cam.far = pose.far ?? 400;
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld(true);
};

export const Rig = ({pose}) => {
  const {camera} = useThree();
  applyPose(camera, pose);
  useFrame(() => applyPose(camera, pose), -1);
  return null;
};

// JS-side projection for HTML labels (same maths as the GL camera)
const tmpCam = new THREE.PerspectiveCamera(40, 16 / 9, 0.05, 400);
const v = new THREE.Vector3();
export const project = (pose, p, W = 1920, H = 1080) => {
  tmpCam.aspect = W / H;
  applyPose(tmpCam, pose);
  v.set(p[0], p[1], p[2]).project(tmpCam);
  const camSpace = new THREE.Vector3(p[0], p[1], p[2]).applyMatrix4(tmpCam.matrixWorldInverse);
  return {x: (v.x * 0.5 + 0.5) * W, y: (-v.y * 0.5 + 0.5) * H, depth: -camSpace.z, visible: camSpace.z < 0};
};
